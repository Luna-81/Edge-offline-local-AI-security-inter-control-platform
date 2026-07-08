"""
聊天相关路由
"""
import json
import logging
import time
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

# ✅ 从 dependencies 导入
from dependencies import get_current_user, admin_required

logger = logging.getLogger("AegisNet.Hamilton.Chat")

router = APIRouter(prefix="/api", tags=["chat"])
user_router = APIRouter(prefix="/user-api", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/ai-chat")
async def admin_chat_handler(
    req: Request,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(admin_required),
):
    """管理员聊天接口"""
    # 延迟导入，避免循环依赖
    from main import (
        get_local_vitals, vanguard, on_ebpf_attack,
        local_brain, safe_vault_save, logger as main_logger
    )
    
    vitals = await get_local_vitals()
    v_res = await vanguard.talk(request.question)

    if "威胁" in v_res or "攻击" in v_res:
        threat_score = 0.85
        client_ip = req.client.host if req.client else "unknown"
        await on_ebpf_attack(
            ip=client_ip,
            port=0,
            protocol="unknown",
            attack_type="AI_DETECTED",
            threat_score=threat_score,
        )
    
    answer = await local_brain.talk(
        user_input=request.question, vitals=vitals, vanguard_res=v_res
    )
    content_id = f"{admin.get('username', 'admin')}_{int(time.time() * 1000)}"
    
    background_tasks.add_task(
        safe_vault_save,
        json.dumps({"q": request.question, "a": answer, "content_id": content_id}),
        action="LEARNED_KNOWLEDGE",
    )
    
    return {
        "answer": answer,
        "vitals": vitals,
        "status": "success",
        "content_id": content_id,
    }


@user_router.post("/chat")
async def user_chat_endpoint(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """用户聊天接口"""
    # 延迟导入，避免循环依赖
    from main import process_ai_chat, perform_billing, get_user_balance, sio, logger as main_logger
    
    username = user["username"]
    question = request.question
    
    result = await process_ai_chat(username, question)
    
    if not result.get("from_cache"):
        cost, balance = await perform_billing(username, question)
        tier = user.get("tier", "standard")
    else:
        balance, tier = await get_user_balance(username)
        cost = 0
    
    background_tasks.add_task(
        sio.emit,
        "terminal_update",
        {"type": "AI_RESPONSE", "content": result["answer"]},
        room="admin",
    )
    
    return {
        "answer": result["answer"],
        "status": "success",
        "user_status": {
            "balance_tokens": balance,
            "tier": tier,
        },
        "last_usage": cost,
        "from_cache": result.get("from_cache", False),
    }
