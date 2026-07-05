"""
认证相关路由
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
import jwt

# ✅ 从 dependencies 导入
from dependencies import get_current_user, admin_required

logger = logging.getLogger("AegisNet.Hamilton.Auth")

router = APIRouter(prefix="/api", tags=["auth"])
user_router = APIRouter(prefix="/user-api", tags=["auth"])


@router.post("/login")
@user_router.post("/login")
async def login_endpoint(request: Request):
    """用户登录"""
    # 延迟导入，避免循环依赖
    from main import authenticate_user_logic
    data = await request.json()
    return await authenticate_user_logic(
        data.get("username"),
        data.get("password")
    )


@router.post("/refresh")
@user_router.post("/refresh")
async def refresh_token_endpoint(authorization: Optional[str] = Header(None)):
    """刷新Token"""
    # 延迟导入，避免循环依赖
    from main import config, create_jwt_token, get_redis
    
    if not authorization:
        raise HTTPException(status_code=401, detail="NO_TOKEN")
    
    try:
        old_token = authorization.replace("Bearer ", "").strip()
        payload = jwt.decode(
            old_token,
            config.SECRET_KEY,
            algorithms=[config.ALGORITHM],
            options={"verify_exp": False}
        )

        redis_client = get_redis()
        if redis_client:
            old_jti = payload.get("jti")
            if old_jti:
                if redis_client.sismember("token_blacklist", old_jti):
                    raise HTTPException(status_code=401, detail="TOKEN_REVOKED")

        now = datetime.now(timezone.utc).timestamp()
        exp = payload.get("exp")
        if exp and (now - exp > config.TOKEN_REFRESH_WINDOW_DAYS * 24 * 3600):
            if redis_client and payload.get("jti"):
                redis_client.sadd("token_blacklist", payload.get("jti"))
                redis_client.expire("token_blacklist", config.TOKEN_REFRESH_WINDOW_DAYS * 24 * 3600)
            raise HTTPException(status_code=401, detail="REFRESH_EXPIRED")

        new_jti = f"{payload.get('username')}_{int(now)}"
        new_token = create_jwt_token(
            {
                "username": payload.get("username"),
                "role": payload.get("role"),
                "tier": payload.get("tier"),
                "balance": payload.get("balance"),
            },
            jti=new_jti,
        )

        if redis_client and payload.get("jti"):
            redis_client.sadd("token_blacklist", payload.get("jti"))
            redis_client.expire("token_blacklist", config.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

        return {"access": new_token, "token": new_token, "access_token": new_token}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="INVALID_TOKEN")


@router.get("/profile")
@router.get("/user/profile")
@user_router.get("/profile")
async def profile_endpoint(user: dict = Depends(get_current_user)):
    """获取用户信息"""
    return user

# ============================================================
# 管理员 API（用户管理）
# ============================================================

@router.get("/admin/users")
async def get_admin_users(user: dict = Depends(get_current_user)):
    """获取所有用户列表（仅管理员）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    import aiosqlite
    db_path = "/home/rick/knowpasser/users.db"
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, username, role, balance_tokens FROM users"
        )
        rows = await cursor.fetchall()
        
        return [{
            "id": row["id"],
            "username": row["username"],
            "role": row["role"] or "user",
            "tokens": row["balance_tokens"] or 0
        } for row in rows]


@router.patch("/admin/users/{user_id}/topup")
async def topup_user(
    user_id: int,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """充值 Token（仅管理员）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    data = await request.json()
    amount = data.get("amount", 0)
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于0")
    
    import aiosqlite
    db_path = "/home/rick/knowpasser/users.db"
    
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE users SET balance_tokens = balance_tokens + ? WHERE id = ?",
            (amount, user_id)
        )
        await db.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        return {"success": True, "message": f"成功充值 {amount} Token"}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    user: dict = Depends(get_current_user)
):
    """删除用户（仅管理员）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    import aiosqlite
    db_path = "/home/rick/knowpasser/users.db"
    
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,)
        )
        await db.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        return {"success": True, "message": "用户已删除"}

# ============================================================
# 数据标注 API
# ============================================================

@router.get("/latest-data")
async def get_latest_data(user: dict = Depends(get_current_user)):
    """获取最新的未标注数据"""
    try:
        import json
        import lancedb
        
        db_path = "/home/rick/knowpasser/src/agent/ai/vault_lancedb"
        db = lancedb.connect(db_path)
        
        # 获取已标注的 content_id 列表
        try:
            feedback_table = db.open_table("content_feedback")
            df_feedback = feedback_table.to_pandas()
            labeled_ids = set(df_feedback['content_id'].tolist()) if not df_feedback.empty else set()
        except:
            labeled_ids = set()
        
        # 获取未标注的数据
        table = db.open_table("hamilton_knowledge")
        df = table.to_pandas().sort_values('seq', ascending=False)
        
        # 过滤掉已标注的
        if labeled_ids:
            df = df[~df['id'].isin(labeled_ids)]
        
        if df.empty:
            return {"id": None, "data": "暂无未标注数据", "all_labeled": True}
        
        row = df.iloc[0]
        row_dict = row.to_dict()
        
        text_data = {}
        try:
            text_data = json.loads(row_dict.get('text', '{}'))
        except:
            pass
        
        return {
            "id": row_dict.get('id'),
            "data": text_data,
            "cpu_val": row_dict.get('cpu_val'),
            "entropy": row_dict.get('entropy'),
            "intent": row_dict.get('intent')
        }
    except Exception as e:
        logger.error(f"获取最新数据失败: {e}")
        return {"id": None, "data": "获取失败"}


@router.post("/annotate")
async def store_annotation(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """存储用户标注"""
    data = await request.json()
    content_id = data.get('content_id')
    label = data.get('label')
    
    if not content_id or not label:
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    try:
        import lancedb
        import pyarrow as pa
        import time
        
        db_path = "/home/rick/knowpasser/src/agent/ai/vault_lancedb"
        db = lancedb.connect(db_path)
        table_name = "content_feedback"
        
        # 检查表是否存在
        if table_name not in db.table_names():
            schema = pa.schema([
                pa.field("content_id", pa.string()),
                pa.field("user_label", pa.string()),
                pa.field("timestamp", pa.float64()),
                pa.field("username", pa.string()),
            ])
            db.create_table(table_name, schema=schema)
        
        table = db.open_table(table_name)
        table.add([{
            "content_id": content_id,
            "user_label": label,
            "timestamp": time.time(),
            "username": user.get('username')
        }])
        
        logger.info(f"📝 用户 {user.get('username')} 标注 {content_id} 为 {label}")
        return {"success": True, "message": f"已标注为 {label}"}
        
    except Exception as e:
        logger.error(f"标注存储失败: {e}")
        raise HTTPException(status_code=500, detail="标注存储失败")
