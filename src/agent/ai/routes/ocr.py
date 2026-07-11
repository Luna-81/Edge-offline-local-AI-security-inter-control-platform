# routes/ocr.py
# -*- coding: utf-8 -*-
"""
OCR API 路由 - 转发到独立服务
"""

import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from routes.dependencies import get_current_user

logger = logging.getLogger("Routes.OCR")
router = APIRouter(prefix="/api/ocr", tags=["ocr"])

OCR_SERVICE_URL = "http://localhost:8005/api/ocr"


@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """OCR 图片识别（转发）"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    try:
        # 读取文件内容
        content = await file.read()
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 构建 multipart/form-data
            files = {
                'file': (file.filename, content, file.content_type)
            }
            response = await client.post(
                f"{OCR_SERVICE_URL}/analyze",
                files=files
            )
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        logger.error("OCR 服务超时")
        raise HTTPException(status_code=504, detail="OCR 服务超时")
    except httpx.HTTPStatusError as e:
        logger.error(f"OCR 服务错误: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        logger.error(f"OCR 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def ocr_batch(
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user)
):
    """批量 OCR（转发）"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 构建 multipart
            files_payload = []
            for f in files:
                content = await f.read()
                files_payload.append(
                    ('files', (f.filename, content, f.content_type))
                )
            
            response = await client.post(
                f"{OCR_SERVICE_URL}/batch",
                files=files_payload
            )
            response.raise_for_status()
            return response.json()
            
    except Exception as e:
        logger.error(f"批量 OCR 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def ocr_health():
    """OCR 健康检查（转发）"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OCR_SERVICE_URL}/health")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
