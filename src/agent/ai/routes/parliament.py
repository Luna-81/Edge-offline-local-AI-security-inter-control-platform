"""
议会相关路由
"""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("AegisNet.Hamilton.Parliament")

router = APIRouter(prefix="/api/parliament", tags=["parliament"])


class ParliamentExecuteRequest(BaseModel):
    """六议会执行请求"""
    question: str
    strategy: Optional[str] = "weighted_vote"


@router.post("/execute")
async def parliament_execute_endpoint(request: ParliamentExecuteRequest):
    """六议会执行 API"""
    try:
        import local_brain
        
        result = await local_brain.parliament_execute_sync(request.question, request.strategy)
        
        return {
            "status": "success",
            "final_decision": result.get("final_decision", "unknown"),
            "confidence": result.get("confidence_score", 0),
            "executable": result.get("executable", {}),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 议会执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def parliament_status():
    """获取六议会状态"""
    return {
        "status": "ready",
        "mode": "execute",
        "available_strategies": ["weighted_vote", "consensus", "statistical"]
    }
