"""
共享依赖 - 避免循环导入
"""
import jwt
import logging
from fastapi import HTTPException, Header, Depends
from typing import Optional

logger = logging.getLogger("AegisNet.Hamilton.Dependencies")

# 延迟导入，避免循环依赖
_config = None
_redis_manager = None


def _get_config():
    """延迟获取 config"""
    global _config
    if _config is None:
        from main import config
        _config = config
    return _config


def _get_redis():
    """延迟获取 Redis 客户端"""
    global _redis_manager
    if _redis_manager is None:
        from main import get_redis
        _redis_manager = get_redis
    return _redis_manager()


def decode_token(token: str):
    """解码并验证 JWT"""
    try:
        config = _get_config()
        clean_token = token.replace("Bearer ", "").strip()
        payload = jwt.decode(
            clean_token,
            config.SECRET_KEY,
            algorithms=[config.ALGORITHM]
        )

        redis_client = _get_redis()
        if redis_client:
            jti = payload.get("jti")
            if jti:
                is_blacklisted = redis_client.sismember("token_blacklist", jti)
                if is_blacklisted:
                    logger.warning(f"⚠️ Token {jti} is blacklisted")
                    return None

        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


async def get_current_user(authorization: Optional[str] = Header(None)):
    """获取当前用户信息"""
    if not authorization:
        raise HTTPException(status_code=401, detail="MISSING_AUTH_HEADER")
    payload = decode_token(authorization)
    if not payload:
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED_OR_INVALID")
    return payload


async def admin_required(current_user: dict = Depends(get_current_user)):
    """管理员权限验证"""
    role = current_user.get("role") or current_user.get("tier")
    if role != "admin":
        raise HTTPException(status_code=403, detail="INSUFFICIENT_PERMISSIONS")
    return current_user
