"""
Harness 编排 API 路由
"""
import logging
import sys
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
# ✅ 确保 harness 在路径中
HARNESS_PATH = "/home/rick/knowpasser/src/harness"
if HARNESS_PATH not in sys.path:
    sys.path.insert(0, HARNESS_PATH)

SRC_PATH = "/home/rick/knowpasser/src"
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

logger = logging.getLogger("AegisNet.Hamilton.Harness")

router = APIRouter(prefix="/api/harness", tags=["harness"])


class HarnessRequest(BaseModel):
    """Harness 编排请求"""
    question: str
    max_loops: Optional[int] = 3
    confidence_threshold: Optional[float] = 0.6


@router.post("/orchestrate")
async def harness_orchestrate_endpoint(request: HarnessRequest):
    """
    Harness 编排 API
    任务拆解 → 逐项讨论 → 逐项执行 → 汇总报告
    """
    try:
        # 确保 harness 在路径中
        harness_path = "/home/rick/knowpasser/src/harness"
        if harness_path not in sys.path:
            sys.path.insert(0, harness_path)
        
        from harness.api import create_harness_orchestrator
        
        orchestrator = create_harness_orchestrator({
            "max_loops": request.max_loops,
            "confidence_threshold": request.confidence_threshold
        })
        
        result = await orchestrator.run(
            question=request.question,
            max_loops=request.max_loops,
            confidence_threshold=request.confidence_threshold
        )
        
        return {
            "status": result.get("status", "success"),
            "user_input": request.question,
            "tasks": result.get("tasks", []),
            "executed_count": result.get("executed_count", 0),
            "skipped_count": result.get("skipped_count", 0),
            "report": result.get("report", {}),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Harness 编排失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
