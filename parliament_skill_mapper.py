# /home/rick/knowpasser/src/agent/ai/haystack_pipeline/roundtable/parliament_skill_mapper.py
"""
议会决策 → MCP 技能映射
"""
import re
from typing import Dict, Any, Optional, List

# 技能映射表
SKILL_MAPPING = {
    # ====== 安全类 ======
    "封锁IP": {
        "skill": "block_ip",
        "params": {"ip": "ip", "reason": "reason"},
        "description": "封锁恶意 IP"
    },
    "验证IP": {
        "skill": "validate_ip",
        "params": {"ip": "ip"},
        "description": "验证 IP 地址格式"
    },
    "查询威胁情报": {
        "skill": "query_threat_intelligence",
        "params": {"query": "query", "limit": "limit"},
        "description": "查询威胁情报"
    },
    "多源威胁查询": {
        "skill": "query_multi_source_threat",
        "params": {"ip": "ip"},
        "description": "多源威胁情报查询"
    },
    "分析哈希": {
        "skill": "analyze_hash",
        "params": {"hash_value": "hash", "hash_type": "hash_type"},
        "description": "分析文件哈希"
    },
    "高级哈希分析": {
        "skill": "analyze_hash_advanced",
        "params": {"hash_value": "hash", "hash_type": "hash_type"},
        "description": "高级哈希分析（含彩虹表）"
    },
    "检测可疑模式": {
        "skill": "detect_suspicious_pattern",
        "params": {"text": "text"},
        "description": "检测文本中的 IOC"
    },
    "威胁狩猎": {
        "skill": "threat_hunting",
        "params": {"criteria": "criteria"},
        "description": "主动威胁狩猎"
    },
    "智能封堵": {
        "skill": "smart_block_decision",
        "params": {"ip": "ip", "context": "context"},
        "description": "智能封堵决策"
    },
    
    # ====== 系统类 ======
    "执行脚本": {
        "skill": "execute_shell_script",
        "params": {"script_content": "script", "script_name": "script_name"},
        "description": "执行 Shell 脚本"
    },
    "设置定时任务": {
        "skill": "setup_cron_job",
        "params": {"job_spec": "job_spec", "command": "command", "comment": "comment"},
        "description": "设置 crontab 定时任务"
    },
    "系统优化": {
        "skill": "optimize_system",
        "params": {"optimization_type": "optimization_type", "params": "params"},
        "description": "系统优化（清理缓存、swap等）"
    },
    "执行决策": {
        "skill": "execute_decision",
        "params": {"decision": "decision"},
        "description": "执行议会决策"
    },
    
    # ====== 分析类 ======
    "关联告警": {
        "skill": "correlate_alerts",
        "params": {"alerts": "alerts"},
        "description": "告警关联分析"
    },
    "异常检测": {
        "skill": "detect_anomaly",
        "params": {"data": "data", "model_type": "model_type"},
        "description": "机器学习异常检测"
    },
    "执行剧本": {
        "skill": "execute_playbook",
        "params": {"playbook_name": "playbook_name", "parameters": "parameters"},
        "description": "执行响应剧本"
    },
    
    # ====== 系统状态 ======
    "系统状态": {
        "skill": "get_system_status",
        "params": {},
        "description": "获取系统运行状态"
    },
}


def match_skill(decision: str) -> Optional[Dict[str, Any]]:
    """根据决策文本匹配对应的 MCP 技能（支持中英文）"""
    # 1. 精确匹配
    for key, config in SKILL_MAPPING.items():
        if key in decision:
            return config
    
    # 2. 英文关键词映射
    en_mapping = {
        "firewall": "封锁IP", "block": "封锁IP",
        "validate": "验证IP", "verif": "验证IP",
        "threat": "查询威胁情报", "intel": "查询威胁情报",
        "hash": "分析哈希", "md5": "分析哈希", "sha": "分析哈希",
        "script": "执行脚本", "shell": "执行脚本",
        "cron": "设置定时任务", "schedule": "设置定时任务",
        "optimize": "系统优化", "performance": "系统优化", "cache": "系统优化",
        "hunt": "威胁狩猎", "hunting": "威胁狩猎",
        "playbook": "执行剧本", "response": "执行剧本",
        "status": "系统状态", "health": "系统状态",
        "anomaly": "异常检测", "outlier": "异常检测",
        "correlate": "关联告警", "alert": "关联告警",
    }
    
    decision_lower = decision.lower()
    for en_key, cn_key in en_mapping.items():
        if en_key in decision_lower:
            return SKILL_MAPPING.get(cn_key)
    
    return None



def extract_params(decision: str, result: Dict[str, Any], param_template: Dict[str, str]) -> Dict[str, Any]:
    """
    从决策和结果中提取参数
    支持从文本中提取 IP、哈希、域名等
    """
    params = {}
    
    for skill_param, source_field in param_template.items():
        value = ""
        
        # 1. 从 result 中获取
        if source_field in result and result[source_field]:
            value = result[source_field]
        
        # 2. 从 decision 中提取具体值
        else:
            # 2.1 提取 IP 地址
            if skill_param == "ip" or "ip" in skill_param.lower():
                ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                ip_match = re.search(ip_pattern, decision)
                if ip_match:
                    value = ip_match.group()
            
            # 2.2 提取哈希值
            elif skill_param == "hash" or "hash" in skill_param.lower():
                hash_patterns = [
                    r'\b[a-fA-F0-9]{32}\b',   # MD5
                    r'\b[a-fA-F0-9]{40}\b',   # SHA1
                    r'\b[a-fA-F0-9]{64}\b',   # SHA256
                ]
                for pattern in hash_patterns:
                    hash_match = re.search(pattern, decision)
                    if hash_match:
                        value = hash_match.group()
                        break
            
            # 2.3 提取域名
            elif skill_param == "domain" or "domain" in skill_param.lower():
                domain_pattern = r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b'
                domain_match = re.search(domain_pattern, decision)
                if domain_match:
                    value = domain_match.group()
            
            # 2.4 提取脚本内容 (如果有)
            elif skill_param == "script" or "script_content" in skill_param.lower():
                # 查找代码块或引号内的内容
                script_match = re.search(r'```(?:bash|sh|shell)?\s*([\s\S]*?)\s*```', decision)
                if script_match:
                    value = script_match.group(1).strip()
                else:
                    # 尝试找引号内的内容
                    quote_match = re.search(r'["\']([^"\']*)["\']', decision)
                    if quote_match:
                        value = quote_match.group(1)
            
            # 2.5 提取优化类型
            elif skill_param == "optimization_type":
                opt_types = ["clear_cache", "swap_optimize", "file_cleanup", "log_rotate", "memory_optimize"]
                for opt in opt_types:
                    if opt in decision.lower():
                        value = opt
                        break
                if not value:
                    # 尝试从中文提取
                    if "缓存" in decision:
                        value = "clear_cache"
                    elif "swap" in decision.lower():
                        value = "swap_optimize"
            
            # 2.6 提取时间规格 (cron)
            elif skill_param == "job_spec" or "spec" in skill_param.lower():
                # 查找 cron 格式: * * * * *
                cron_pattern = r'(\*|[0-9]+|\*/[0-9]+)\s+(\*|[0-9]+|\*/[0-9]+)\s+(\*|[0-9]+|\*/[0-9]+)\s+(\*|[0-9]+|\*/[0-9]+)\s+(\*|[0-9]+|\*/[0-9]+)'
                cron_match = re.search(cron_pattern, decision)
                if cron_match:
                    value = cron_match.group()
            
            # 2.7 如果都没匹配，从 decision 中提取关键词作为值
            if not value:
                # 尝试取 decision 的前50个字符
                value = decision[:50]
        
        params[skill_param] = value
    
    return params


async def execute_decision_with_mcp(decision: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行决策 - 匹配并调用 MCP 技能
    
    Args:
        decision: 决策文本（如 "封锁IP"）
        result: 议会收敛结果
    
    Returns:
        技能执行结果
    """
    from .parliament_mcp_client import mcp_call
    
    # 匹配技能
    skill_config = match_skill(decision)
    
    if not skill_config:
        return {
            "status": "pending",
            "message": f"未找到匹配的技能: {decision}",
            "decision": decision,
            "available_skills": list(SKILL_MAPPING.keys())
        }
    
    # 提取参数
    params = extract_params(decision, result, skill_config["params"])
    
    # 调用 MCP 技能
    return await mcp_call(skill_config["skill"], **params)


def execute_decision_with_mcp_sync(decision: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    同步版本：执行决策
    """
    import asyncio
    
    # ✅ 修复：使用新的事件循环，避免 "Event loop is closed" 错误
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(execute_decision_with_mcp(decision, result))
    finally:
        loop.close()
