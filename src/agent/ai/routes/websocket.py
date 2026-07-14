"""
WebSocket 事件处理器
"""

import logging
import json
import asyncio
import time
import sys  # ✅ 添加
from datetime import datetime
from typing import Optional

# ✅ 确保 harness 在路径中
HARNESS_PATH = "/home/rick/knowpasser/src/harness"
if HARNESS_PATH not in sys.path:
    sys.path.insert(0, HARNESS_PATH)

SRC_PATH = "/home/rick/knowpasser/src"
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

logger = logging.getLogger("AegisNet.Hamilton.WebSocket")


def register_websocket_events(sio, handle_errors):
    """
    注册所有 WebSocket 事件

    Args:
        sio: Socket.IO 服务器实例
        handle_errors: 错误处理装饰器
    """

    @sio.event
    async def connect(sid, environ, auth):
        """WebSocket 连接认证"""
        from main import decode_token, logger

        token = None

        # 从多个来源获取 token
        if auth:
            if isinstance(auth, dict):
                token = (
                    auth.get("token")
                    or auth.get("Authorization")
                    or auth.get("access_token")
                )
            elif isinstance(auth, str):
                token = auth

        if not token:
            auth_header = environ.get("HTTP_AUTHORIZATION", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            query_string = environ.get("QUERY_STRING", "")
            if "token=" in query_string:
                import urllib.parse

                parsed = urllib.parse.parse_qs(query_string)
                token = parsed.get("token", [None])[0]

        if not token:
            cookie_header = environ.get("HTTP_COOKIE", "")
            if "token=" in cookie_header:
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if part.startswith("token="):
                        token = part[6:]
                        break

        if not token:
            logger.warning(f"⚠️ [SID: {sid}] No token provided")
            return False

        # 验证 token
        payload = decode_token(token)
        if not payload:
            logger.warning(f"⚠️ [SID: {sid}] Invalid token")
            return False

        # 存储会话信息
        username = payload.get("username")
        role = payload.get("role", "guest")
        tier = payload.get("tier", "free")

        async with sio.session(sid) as session:
            session["username"] = username
            session["role"] = role
            session["tier"] = tier
            session["user_id"] = payload.get("user_id", "unknown")

        await sio.enter_room(sid, f"user_{username}")
        await sio.enter_room(sid, "broadcast_metrics")

        if role == "admin":
            await sio.enter_room(sid, "admin_room")

        logger.info(f"✅ User connected: {username} (role={role}, sid={sid})")
        return True

    @sio.on("chat_request")
    @handle_errors(log_message="WebSocket chat error")
    async def on_chat_request(sid, data):
        """处理 WebSocket 聊天请求"""
        from main import (
            process_ai_chat,
            store_feedback,
            config,
            db_pool,
            get_user_balance,
            ws_batch_emitter,
            logger,
        )

        session = await sio.get_session(sid)
        username = session.get("username")
        role = session.get("role", "user")

        if not username:
            await sio.emit(
                "ai_response",
                {"answer": "⚠️ 会话无效，请重新登录", "status": "error"},
                room=sid,
            )
            return

        question = data.get("question", "").strip()
        if not question:
            return

        # 处理反馈命令
        if question.startswith("!good") or question.startswith("!bad"):
            parts = question.replace(":", " ").split()
            content_id = parts[1] if len(parts) >= 2 else "unknown"
            feedback_type = "good" if question.startswith("!good") else "bad"

            await store_feedback(content_id, feedback_type, username)

            await sio.emit(
                "ai_response",
                {
                    "answer": f"感谢您的{'👍' if feedback_type == 'good' else '👎'}反馈！我们会持续改进。",
                    "last_usage": 0,
                    "user_status": {"balance_tokens": 0, "tier": role},
                },
                room=sid,
            )
            return

        # 先调用 AI（会检查缓存）
        result = await process_ai_chat(username, question)

        # 根据缓存状态计费（只有这一次）
        if not result.get("from_cache"):
            cost = config.DEFAULT_CHAT_COST
            async with db_pool.connection() as db:
                cursor = await db.execute(
                    "UPDATE users SET balance_tokens = balance_tokens - ? "
                    "WHERE username = ? AND balance_tokens >= ?",
                    (cost, username, cost),
                )
                await db.commit()

                if cursor.rowcount == 0:
                    balance, tier = await get_user_balance(username)
                    await sio.emit(
                        "ai_response",
                        {
                            "answer": f"⚠️ 余额不足，当前余额：{balance} tokens，需要 {cost} tokens",
                            "last_usage": 0,
                            "user_status": {
                                "balance_tokens": balance,
                                "tier": tier,
                            },
                        },
                        room=sid,
                    )
                    return

                new_balance, tier = await get_user_balance(username)
        else:
            cost = 0
            new_balance, tier = await get_user_balance(username)

        # 发送响应
        await sio.emit(
            "ai_response",
            {
                "answer": result["answer"],
                "content_id": result["content_id"],
                "last_usage": cost,
                "from_cache": result.get("from_cache", False),
                "user_status": {
                    "balance_tokens": new_balance,
                    "tier": tier,
                    "username": username,
                },
            },
            room=sid,
        )

        logger.info(f"✅ Chat response sent to {username}, new balance: {new_balance}")

    @sio.on("ping")
    async def on_ping(sid, data=None):
        """心跳检测"""
        await sio.emit("pong", {"timestamp": datetime.now().isoformat()}, room=sid)

    @sio.on("balance_query")
    async def on_balance_query(sid, data=None):
        """查询余额"""
        try:
            from main import db_pool, logger

            session = await sio.get_session(sid)
            username = session.get("username")

            if not username:
                return

            async with db_pool.connection() as db:
                async with db.execute(
                    "SELECT balance_tokens, tier FROM users WHERE username = ?",
                    (username,),
                ) as cursor:
                    user = await cursor.fetchone()

            if user:
                await sio.emit(
                    "balance_update",
                    {
                        "balance_tokens": user["balance_tokens"],
                        "tier": user["tier"],
                        "username": username,
                    },
                    room=sid,
                )
        except Exception as e:
            logger.error(f"❌ Balance query error: {e}")

    @sio.on("parliament_discuss")
    async def on_parliament_discuss(sid, data):
        """6议会讨论 - 调用 local_brain 的线程"""
        from main import logger, local_brain

        session = await sio.get_session(sid)
        username = session.get("username")

        if not username:
            await sio.emit("parliament_error", {"message": "请先登录"}, room=sid)
            return

        question = data.get("question", "").strip()
        if not question:
            await sio.emit("parliament_error", {"message": "问题不能为空"}, room=sid)
            return

        logger.info(f"🏛️ 议会讨论开始: {username} - {question[:50]}...")
        await sio.emit(
            "parliament_event",
            {"type": "start", "message": f"🏛️ 议会讨论开始: {username}"},
            room=sid,
        )

        try:
            result = await local_brain.parliament_discuss_sync(question, username)

            if result.get("status") == "error":
                await sio.emit(
                    "parliament_error",
                    {"message": result.get("error", "未知错误")},
                    room=sid,
                )
                return

            for event in result.get("events", []):
                await sio.emit("parliament_event", event, room=sid)

            logger.info(f"🏛️ 议会讨论完成: {username}")

        except Exception as e:
            logger.error(f"❌ 议会讨论失败: {e}")
            await sio.emit("parliament_error", {"message": str(e)}, room=sid)

    @sio.on("parliament_execute")
    async def on_parliament_execute(sid, data):
        """六议会执行 - Socket.IO 版本"""
        from main import logger, local_brain

        session = await sio.get_session(sid)
        username = session.get("username")

        if not username:
            await sio.emit("parliament_error", {"message": "请先登录"}, room=sid)
            return

        question = data.get("question", "").strip()
        if not question:
            await sio.emit("parliament_error", {"message": "问题不能为空"}, room=sid)
            return

        strategy = data.get("strategy", "weighted_vote")

        logger.info(f"⚡ 议会执行开始: {username} - {question[:50]}...")
        await sio.emit(
            "parliament_event",
            {"type": "start", "message": f"⚡ 议会执行启动: {username}"},
            room=sid,
        )

        try:
            result = await local_brain.parliament_execute_sync(question, strategy)

            if result.get("status") == "error":
                await sio.emit(
                    "parliament_error",
                    {"message": result.get("error", "未知错误")},
                    room=sid,
                )
                return

            for event in result.get("events", []):
                await sio.emit("parliament_event", event, room=sid)

            logger.info(f"⚡ 议会执行完成: {username}")

        except Exception as e:
            logger.error(f"❌ 议会执行失败: {e}")
            await sio.emit("parliament_error", {"message": str(e)}, room=sid)

    @sio.on("harness_editor")
    async def on_harness_editor(sid, data):
        """六议会编辑模式 - 完整执行循环"""
        from main import logger

        session = await sio.get_session(sid)
        username = session.get("username")

        if not username:
            await sio.emit("editor_error", {"message": "请先登录"}, room=sid)
            return

        question = data.get("question", "").strip()
        max_loops = data.get("max_loops", 3)

        if not question:
            await sio.emit("editor_error", {"message": "问题不能为空"}, room=sid)
            return

        logger.info(f"✏️ 六议会编辑模式启动: {username} - {question[:50]}...")

        try:
            from harness.editor import create_editor

            editor = create_editor(config={"max_loops": max_loops}, socket=sio)

            result = await editor.edit(question, max_loops)

            await sio.emit(
                "editor_complete",
                {
                    "session_id": result.session_id,
                    "loops": result.loops,
                    "executable": result.executable,
                    "report": result.final_report,
                },
                room=sid,
            )

            logger.info(f"✅ 六议会编辑模式完成: {username}")

        except Exception as e:
            logger.error(f"❌ 六议会编辑模式失败: {e}")
            await sio.emit("editor_error", {"message": str(e)}, room=sid)

    @sio.on("sentinel_data")
    async def on_sentinel_data(sid, raw_data):
        """接收 Sentinel 数据"""
        from main import safe_vault_save, logger

        try:
            await safe_vault_save(raw_data, action="SENTINEL_STREAM")
        except Exception as e:
            logger.error(f"❌ Sentinel Data Stream Error: {e}")

    @sio.event
    async def disconnect(sid):
        """WebSocket 断开连接"""
        logger.info(f"❌ WS Disconnected: {sid}")
