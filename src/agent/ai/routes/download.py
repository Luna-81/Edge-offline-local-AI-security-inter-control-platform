"""
下载相关路由
"""
import logging
import os
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# 从 dependencies 导入
from dependencies import get_current_user

logger = logging.getLogger("AegisNet.Hamilton.Download")

router = APIRouter(prefix="/api/download", tags=["download"])


def get_download_dirs() -> list:
    """获取所有可下载文件的目录列表"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(current_dir, "discussions"),
        os.path.join(current_dir, "haystack_pipeline", "discussions"),
        "/home/rick/knowpasser/src/agent/ai/discussions",
        "/home/rick/knowpasser/src/agent/ai/haystack_pipeline/discussions",
    ]


def find_download_file(filename: str) -> Optional[str]:
    """查找文件，返回完整路径，找不到返回 None"""
    # 安全检查：防止路径穿越攻击
    if not (filename.startswith("discussion_") or filename.startswith("execution_")):
        return None
    if not filename.endswith(".json"):
        return None
    if ".." in filename or "/" in filename:
        return None
    
    for discussions_dir in get_download_dirs():
        if not os.path.exists(discussions_dir):
            continue
        filepath = os.path.join(discussions_dir, filename)
        if os.path.exists(filepath):
            return filepath
    return None


@router.get("/list")
async def list_downloadable_files(user: dict = Depends(get_current_user)):
    """获取所有可下载的讨论/执行记录文件列表"""
    from datetime import datetime
    
    files_dict = {}
    
    for discussions_dir in get_download_dirs():
        if not os.path.exists(discussions_dir):
            continue
        
        for filename in os.listdir(discussions_dir):
            if not (filename.startswith("discussion_") or filename.startswith("execution_")):
                continue
            if not filename.endswith(".json"):
                continue
            if filename in files_dict:
                continue
            
            filepath = os.path.join(discussions_dir, filename)
            stat = os.stat(filepath)
            file_type = "execution" if filename.startswith("execution_") else "discussion"
            
            try:
                time_str = filename.split("_")[1].split(".")[0]
                file_time = datetime.strptime(time_str, "%Y%m%d_%H%M%S")
            except (IndexError, ValueError):
                file_time = datetime.fromtimestamp(stat.st_mtime)
            
            files_dict[filename] = {
                "filename": filename,
                "type": file_type,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "time": file_time.isoformat()
            }
    
    files = list(files_dict.values())
    files.sort(key=lambda x: x["modified"], reverse=True)
    
    return {
        "status": "success",
        "files": files,
        "count": len(files)
    }


@router.get("/{filename}")
async def download_json(filename: str):
    """下载讨论记录或执行记录JSON文件"""
    filepath = find_download_file(filename)
    if not filepath:
        return JSONResponse(
            {"error": f"文件不存在: {filename}"},
            status_code=404
        )
    
    return FileResponse(
        filepath,
        media_type="application/json",
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/batch")
async def download_batch(request: Request, user: dict = Depends(get_current_user)):
    """批量下载 JSON 文件"""
    data = await request.json()
    filenames = data.get("files", [])
    
    if not filenames or not isinstance(filenames, list):
        raise HTTPException(status_code=400, detail="No valid files array specified")
    
    results = {}
    for filename in filenames:
        filepath = find_download_file(filename)
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    results[filename] = json.load(f)
            except Exception as e:
                results[filename] = {"error": f"Failed to read file: {str(e)}"}
    
    if not results:
        raise HTTPException(status_code=404, detail="None of the requested files were found")
    
    return results

# ==============================
# 兼容旧前端路径（/api/discussions/stats → 重定向到 /api/download/discussions/stats）
# ==============================

@router.get("/legacy/stats")
async def discussions_stats_legacy(user: dict = Depends(get_current_user)):
    """获取讨论文件存储统计（兼容旧前端路径 /api/discussions/stats）"""
    # 这个路由实际上不会被直接调用，而是被 main.py 中的 @fastapi_app.get 覆盖
    # 保留此函数是为了让代码逻辑统一
    return await discussions_stats(user)


@router.get("/discussions/stats")
async def discussions_stats(user: dict = Depends(get_current_user)):
    """获取讨论文件存储统计（新路径 /api/download/discussions/stats）"""
    import os
    
    total_size = 0
    count = 0
    for discussions_dir in get_download_dirs():
        if not os.path.exists(discussions_dir):
            continue
        for root, dirs, files in os.walk(discussions_dir):
            for file in files:
                if file.endswith(".json"):
                    filepath = os.path.join(root, file)
                    total_size += os.path.getsize(filepath)
                    count += 1
    
    return {
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "max_size_mb": 2048,
        "used_percent": round((total_size / (1024 * 1024 * 2048)) * 100, 2),
        "file_count": count
    }
