# /home/rick/knowpasser/src/agent/ai/haystack_pipeline/roundtable/parliament_mcp_client.py
"""
六议会 MCP 客户端 - 通过 HTTP 调用 MCP Server 执行技能
"""

import os
import json
import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

# 加载 .env
load_dotenv("/home/rick/knowpasser/.env")

# 然后获取 token
MCP_TOKEN = os.getenv("INTERNAL_TOKEN", "")

logger = logging.getLogger("Roundtable.MCP")

# MCP Server 配置
MCP_API_URL = os.getenv("MCP_API_URL", "http://localhost:7999")
MCP_CALL_ENDPOINT = f"{MCP_API_URL}/api/call"
MCP_SKILLS_ENDPOINT = f"{MCP_API_URL}/api/skills"
MCP_TOKEN = os.getenv("INTERNAL_TOKEN", "")

if not MCP_TOKEN:
    logger.warning("⚠️ INTERNAL_TOKEN 未设置，MCP 调用可能失败")


class MCPClient:
    """MCP Server HTTP 客户端"""
    
    def __init__(self, base_url: str = None, token: str = None):
        self.base_url = base_url or MCP_API_URL
        self.token = token or MCP_TOKEN
        self.call_endpoint = f"{self.base_url}/api/call"
        self.skills_endpoint = f"{self.base_url}/api/skills"
        self._skills_cache = None
        self._cache_time = None
        
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "X-Internal-Token": self.token,
            "Content-Type": "application/json"
        }
    
    async def call_skill(self, skill_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 技能
        """
        logger.info(f"🔧 MCP 调用: {skill_name}, 参数: {arguments}")
    
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
            # 确保 arguments 是字典
                if not isinstance(arguments, dict):
                    arguments = {}
            
                payload = {
                    "name": skill_name,
                    "arguments": arguments
                }
            
                response = await client.post(
                    self.call_endpoint,
                    json=payload,
                    headers=self._get_headers()
                )
            
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ MCP 调用成功: {skill_name}")
                    return result
                else:
                    error_msg = f"MCP API 错误: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {
                        "status": "error",
                        "skill": skill_name,
                        "message": error_msg,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
            except Exception as e:
                logger.error(f"❌ MCP 调用失败: {e}")
                return {
                    "status": "error",
                    "skill": skill_name,
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }
    async def get_skills(self, refresh: bool = False) -> List[str]:
        """
        获取所有可用技能列表
        
        Args:
            refresh: 是否刷新缓存
        
        Returns:
            技能名称列表
        """
        # 使用缓存
        if not refresh and self._skills_cache is not None:
            return self._skills_cache
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    self.skills_endpoint,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self._skills_cache = data.get("skills", [])
                    self._cache_time = datetime.utcnow()
                    logger.info(f"📋 获取到 {len(self._skills_cache)} 个技能")
                    return self._skills_cache
                else:
                    logger.error(f"获取技能列表失败: {response.status_code}")
                    return []
                    
            except Exception as e:
                logger.error(f"获取技能列表异常: {e}")
                return []
    
    def get_skills_sync(self, refresh: bool = False) -> List[str]:
        """同步获取技能列表"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.get_skills(refresh))


# 全局 MCP 客户端实例
_mcp_client = None

def get_mcp_client() -> MCPClient:
    """获取全局 MCP 客户端实例（单例）"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


async def mcp_call(skill_name: str, **kwargs) -> Dict[str, Any]:
    """
    便捷函数：调用 MCP 技能
    
    Args:
        skill_name: 技能名称
        **kwargs: 技能参数
    
    Returns:
        执行结果
    """
    client = get_mcp_client()
    return await client.call_skill(skill_name, kwargs)


def mcp_call_sync(skill_name: str, **kwargs) -> Dict[str, Any]:
    """
    同步便捷函数：调用 MCP 技能
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(mcp_call(skill_name, **kwargs))
