"""
MCP 内部 API 路由
"""
import logging
import os
import json
import time
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("AegisNet.Hamilton.MCP")

router = APIRouter(prefix="/internal/mcp", tags=["mcp"])


class MCPBlockRequest(BaseModel):
    ip: str
    reason: str = "MCP tool request"
    port: Optional[int] = 0
    protocol: str = "TCP"


class MCPQueryRequest(BaseModel):
    query: str
    limit: int = 5


@router.post("/block_ip")
async def mcp_block_ip(
    request: MCPBlockRequest,
    x_internal_token: str = Header(...)
):
    """MCP Server 调用的 IP 封锁接口"""
    from main import config, on_ebpf_attack, safe_vault_save
    
    if x_internal_token != config.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    
    await on_ebpf_attack(
        ip=request.ip,
        port=request.port,
        protocol=request.protocol,
        attack_type=f"MCP_BLOCK_{request.reason[:30]}",
        threat_score=0.9
    )
    
    await safe_vault_save(
        json.dumps({
            "action": "MCP_BLOCK_IP",
            "ip": request.ip,
            "reason": request.reason,
            "timestamp": time.time()
        }),
        action="MCP_TOOL_CALL"
    )
    
    logger.info(f"🔒 MCP blocked IP: {request.ip} - {request.reason}")
    return {"status": "success", "message": f"IP {request.ip} blocked"}


@router.post("/query_threat")
async def mcp_query_threat(
    request: MCPQueryRequest,
    x_internal_token: str = Header(...)
):
    """MCP Server 调用的威胁情报查询"""
    from main import config, memory_vault
    
    if x_internal_token != config.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    
    try:
        search_result = await memory_vault.search(request.query)
        
        formatted_results = []
        if search_result:
            items = search_result if isinstance(search_result, list) else [search_result]
            for item in items[:request.limit]:
                if isinstance(item, dict):
                    formatted_results.append({
                        "content": item.get("content", str(item)),
                        "score": item.get("score", 1.0),
                        "metadata": item.get("metadata", {})
                    })
                else:
                    formatted_results.append({
                        "content": str(item),
                        "score": 1.0,
                        "metadata": {}
                    })
        
        return {
            "status": "success",
            "query": request.query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
    except Exception as e:
        logger.error(f"❌ MCP query failed: {e}")
        return {
            "status": "error",
            "query": request.query,
            "results": [],
            "error": str(e)
        }


@router.get("/system_status")
async def mcp_system_status(x_internal_token: str = Header(...)):
    """MCP 获取系统状态"""
    from main import config, get_local_vitals, get_redis, _fifo_thread_running
    
    if x_internal_token != config.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    
    vitals = await get_local_vitals()
    redis_client = get_redis()
    
    ebpf_active = os.path.exists(config.FIFO_PATH) and _fifo_thread_running
    
    return {
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "vitals": vitals,
        "redis_connected": redis_client is not None,
        "ebpf_active": ebpf_active
    }
