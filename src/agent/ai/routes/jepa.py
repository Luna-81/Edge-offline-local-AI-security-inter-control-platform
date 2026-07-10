# routes/jepa.py
# -*- coding: utf-8 -*-
"""
JEPA API 路由 - 转发到独立服务
"""

import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from routes.dependencies import get_current_user

logger = logging.getLogger("Routes.JEPA")
router = APIRouter(prefix="/api/jepa", tags=["jepa"])

JEPA_SERVICE_URL = "http://localhost:8005/api/jepa"


class JEPAAddData(BaseModel):
    data: Dict[str, Any]


class JEPAPredictRequest(BaseModel):
    data: Optional[Dict[str, Any]] = None


@router.post("/add")
async def add_data(
    payload: JEPAAddData,
    user: dict = Depends(get_current_user)
):
    """添加数据到 JEPA（转发）"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{JEPA_SERVICE_URL}/add",
                json=payload.model_dump()
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error("JEPA 服务超时")
        raise HTTPException(status_code=504, detail="JEPA 服务超时")
    except httpx.HTTPStatusError as e:
        logger.error(f"JEPA 服务错误: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"JEPA 添加数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict")
async def predict(
    payload: Optional[JEPAPredictRequest] = None,
    user: dict = Depends(get_current_user)
):
    """JEPA 预测（转发）"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{JEPA_SERVICE_URL}/predict",
                json=payload.model_dump() if payload else {}
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error("JEPA 预测超时")
        raise HTTPException(status_code=504, detail="JEPA 预测超时")
    except httpx.HTTPStatusError as e:
        logger.error(f"JEPA 服务错误: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"JEPA 预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(
    user: dict = Depends(get_current_user)
):
    """JEPA 状态（转发）"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{JEPA_SERVICE_URL}/status")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"JEPA 状态查询失败: {e}")
        return {'status': 'error', 'error': str(e)}
