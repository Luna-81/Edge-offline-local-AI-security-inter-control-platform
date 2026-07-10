"""
内部服务接口（供Harness调用）
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("AegisNet.Hamilton.Internal")

# 创建路由器
router = APIRouter(prefix="/internal", tags=["internal"])


class ParliamentExecuteRequest(BaseModel):
    """六议会执行请求"""
    question: str
    strategy: Optional[str] = "weighted_vote"


class ChatRequest(BaseModel):
    question: str


@router.post("/parliament/execute")
async def internal_parliament_execute(
    request: ParliamentExecuteRequest,
    x_internal_token: str = Header(...)
):
    """内部Harness调用的议会接口（免认证）"""
    # 延迟导入，避免循环依赖
    import sys
    sys.path.insert(0, "/home/rick/knowpasser/src/agent/ai")
    from main import config
    import local_brain
    
    if x_internal_token != config.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    
    try:
        result = await local_brain.parliament_execute_sync(request.question, request.strategy)
        
        return {
            "status": "success",
            "final_decision": result.get("final_decision", "unknown"),
            "confidence": result.get("confidence_score", 0),
            "executable": result.get("executable", {}),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 内部议会执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def internal_chat_endpoint(
    request: ChatRequest,
    x_internal_token: str = Header(...)
):
    """内部Harness调用的聊天接口（免认证）"""
    import sys
    sys.path.insert(0, "/home/rick/knowpasser/src/agent/ai")
    from main import config
    from main import process_ai_chat
    
    if x_internal_token != config.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    
    username = "internal_harness"
    result = await process_ai_chat(username, request.question)
    
    return {
        "answer": result["answer"],
        "status": "success",
        "from_cache": result.get("from_cache", False),
        "content_id": result.get("content_id"),
        "context": result.get("context", "")
    }
