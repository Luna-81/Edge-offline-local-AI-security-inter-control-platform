# roundtable/parliament_executor.py
"""完全独立的议会执行器 - 只生成可执行JSON，不执行"""

import json
import asyncio
import logging
import re
import threading
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import Counter, defaultdict
import yaml
import os

# 添加全局锁
_llm_lock = threading.Lock()

logger = logging.getLogger("Roundtable.Parliament")

# ==================== 1. 专家配置（直接从 roles.yaml 加载） ====================
ROLES_YAML_PATH = "/home/rick/knowpasser/src/agent/ai/roles.yaml"

def load_expert_configs() -> List[Dict]:
    """从 roles.yaml 加载6个专家配置"""
    with open(ROLES_YAML_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    roles = config.get('roles', [])[:6]
    logger.info(f"📋 加载了 {len(roles)} 个专家配置")
    return roles

# ==================== 2. LLM 引擎（独立获取） ====================
def get_llm():
    """获取 LLM 实例（从 local_brain）"""
    try:
        import local_brain
        if hasattr(local_brain, 'llm') and local_brain.llm is not None:
            return local_brain.llm
    except Exception as e:
        logger.error(f"获取 LLM 失败: {e}")
    return None

# ==================== 3. 专家调用（独立，直接返回 JSON） ====================
def _build_json_prompt(expert: Dict, question: str) -> str:
    """构建要求返回 JSON 的提示"""
    return f"""<start_of_turn>user
你是一位专业专家，请严格遵守以下角色定位。

### 角色名称
{expert.get('name', '专家')}

### 角色描述
{expert.get('description', '')}

### 回答要求
你必须以标准 JSON 格式输出你的专业意见，包含以下字段：
- "choice": 你的核心决策建议
- "confidence": 你的置信度（0.0-1.0）
- "reasoning": 你的推理过程（50-100字）
- "key_factors": 关键考虑因素（字符串数组）

### 用户问题
{question}

请只输出 JSON，不要有任何其他内容。
<end_of_turn>
<start_of_turn>model
"""

def _call_expert(llm, expert: Dict, question: str) -> Dict[str, Any]:
    """调用单个专家，返回解析后的 JSON"""
    prompt = _build_json_prompt(expert, question)
    
    try:
        with _llm_lock:
            response = llm(
                prompt,
                max_tokens=512,
                temperature=0.3,
                stop=["<end_of_turn>", "<start_of_turn>"],
                echo=False,
            )
        raw_text = response["choices"][0]["text"].strip()
        
        try:
            parsed = json.loads(raw_text)
            return {
                "expert_id": expert.get('id', 0),
                "expert_name": expert.get('name', 'unknown'),
                "raw_text": raw_text,
                "parsed_json": parsed,
                "valid_json": True,
                "confidence": parsed.get("confidence", 0.5)
            }
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', raw_text)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    return {
                        "expert_id": expert.get('id', 0),
                        "expert_name": expert.get('name', 'unknown'),
                        "raw_text": raw_text,
                        "parsed_json": parsed,
                        "valid_json": True,
                        "confidence": parsed.get("confidence", 0.5)
                    }
                except:
                    pass
            
            return {
                "expert_id": expert.get('id', 0),
                "expert_name": expert.get('name', 'unknown'),
                "raw_text": raw_text,
                "parsed_json": {
                    "choice": "无法解析",
                    "confidence": 0.0,
                    "reasoning": raw_text[:100]
                },
                "valid_json": False,
                "confidence": 0.0
            }
    except Exception as e:
        logger.error(f"专家 {expert.get('name')} 调用失败: {e}")
        return {
            "expert_id": expert.get('id', 0),
            "expert_name": expert.get('name', 'unknown'),
            "raw_text": str(e),
            "parsed_json": {
                "choice": "error",
                "confidence": 0.0,
                "reasoning": f"调用失败: {e}"
            },
            "valid_json": False,
            "confidence": 0.0
        }

# ==================== 4. 收敛策略 ====================
def weighted_vote_convergence(responses: List[Dict]) -> Dict[str, Any]:
    """加权投票收敛"""
    vote_count = defaultdict(float)
    details = {}
    confidences = []
    
    for resp in responses:
        if not resp.get('valid_json', False):
            continue
        
        parsed = resp.get('parsed_json', {})
        choice = parsed.get('choice', 'unknown')
        confidence = parsed.get('confidence', 0.5)
        
        vote_count[choice] += confidence
        confidences.append(confidence)
        
        if choice not in details:
            details[choice] = {"votes": 0, "experts": []}
        details[choice]["votes"] += 1
        details[choice]["experts"].append(resp.get('expert_name', 'unknown'))
    
    if not vote_count:
        return {
            "final_decision": "no_consensus",
            "confidence_score": 0,
            "details": details,
            "executable_plan": ["需要重新咨询专家"]
        }
    
    final_choice = max(vote_count, key=vote_count.get)
    total_weighted = sum(vote_count.values())
    consensus_ratio = vote_count[final_choice] / total_weighted if total_weighted > 0 else 0
    
    action_plan = [
        f"执行方案: {final_choice}",
        f"共识度: {consensus_ratio:.2%}",
        f"参与专家数: {len([r for r in responses if r.get('valid_json')])}/6"
    ]
    
    return {
        "final_decision": final_choice,
        "confidence_score": round(consensus_ratio, 3),
        "weighted_votes": {k: round(v, 3) for k, v in vote_count.items()},
        "details": details,
        "executable_plan": action_plan,
        "method": "weighted_vote"
    }

def consensus_summary_convergence(responses: List[Dict]) -> Dict[str, Any]:
    """共识摘要"""
    valid = [r for r in responses if r.get('valid_json')]
    
    if not valid:
        return {
            "final_decision": "no_consensus",
            "confidence_score": 0,
            "executable_plan": ["需要重新咨询专家"]
        }
    
    choices = [r['parsed_json'].get('choice', 'unknown') for r in valid]
    choice_counts = Counter(choices)
    majority = choice_counts.most_common(1)[0][0] if choice_counts else "unknown"
    majority_count = choice_counts.most_common(1)[0][1] if choice_counts else 0
    
    return {
        "final_decision": majority,
        "confidence_score": round(majority_count / 6, 3),
        "vote_distribution": dict(choice_counts),
        "executable_plan": [
            f"采纳多数意见: {majority} ({majority_count}/6 专家支持)",
            "制定详细实施计划",
            "分配资源",
            "设置监控指标"
        ],
        "method": "consensus_summary"
    }

def statistical_convergence(responses: List[Dict]) -> Dict[str, Any]:
    """统计聚合"""
    import statistics
    
    numeric_values = []
    for r in responses:
        if r.get('valid_json'):
            parsed = r.get('parsed_json', {})
            for key in ["score", "value", "confidence"]:
                val = parsed.get(key)
                if val is not None and isinstance(val, (int, float)):
                    numeric_values.append(val)
                    break
    
    if not numeric_values:
        return weighted_vote_convergence(responses)
    
    mean_val = statistics.mean(numeric_values)
    median_val = statistics.median(numeric_values)
    stdev_val = statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0
    
    return {
        "final_decision": round(median_val, 3),
        "confidence_score": round(1 - (stdev_val / (mean_val + 0.001)), 3),
        "statistics": {
            "mean": round(mean_val, 3),
            "median": round(median_val, 3),
            "std_dev": round(stdev_val, 3)
        },
        "executable_plan": [
            f"采用聚合值: {median_val:.2f}",
            f"数据点: {len(numeric_values)} 个"
        ],
        "method": "statistical"
    }

STRATEGIES = {
    "weighted_vote": weighted_vote_convergence,
    "consensus": consensus_summary_convergence,
    "statistical": statistical_convergence
}

def get_strategy(name: str = "weighted_vote"):
    return STRATEGIES.get(name, weighted_vote_convergence)

# ==================== 5. 可执行JSON生成器（完整版） ====================
def generate_executable_json(result: Dict) -> Dict:
    """生成可执行JSON（纯指令，不包含执行结果）"""
    decision = result.get("final_decision", "unknown")
    confidence = result.get("confidence_score", 0)
    
    return {
        "type": "execution",
        "execution_id": f"exec_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.utcnow().isoformat(),
        "decision": str(decision),
        "confidence": confidence,
        "executable": {
            "action": f"EXECUTE_{str(decision).upper().replace(' ', '_')}",
            "steps": result.get("executable_plan", []),
            "params": _extract_params(decision)
        },
        "risk": {
            "level": "HIGH" if confidence > 0.7 else "MEDIUM" if confidence > 0.4 else "LOW",
            "requires_approval": confidence < 0.5
        },
        "pre_execution_report": {
            "expected": {
                "action": decision,
                "confidence": confidence
            },
            "approved_by": "pending",
            "license": False
        },
        "status": "pending_review",
        "method": result.get("method", "unknown")
    }


def _extract_params(decision: str) -> Dict:
    """从决策中提取参数"""
    decision_lower = decision.lower()
    params = {}
    
    if "缓存" in decision or "cache" in decision_lower:
        params["optimization_type"] = "clear_cache"
    elif "swap" in decision_lower:
        params["optimization_type"] = "swap_optimize"
    elif "日志" in decision or "log" in decision_lower:
        params["optimization_type"] = "log_rotate"
    else:
        params["optimization_type"] = decision
    
    # 提取IP（如果有）
    import re
    ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', decision)
    if ip_match:
        params["ip"] = ip_match.group()
    
    return params

# ==================== 6. 主执行器 ====================
class ParliamentExecutor:
    """完全独立的议会执行器 - 只生成可执行JSON"""
    
    def __init__(self, strategy: str = "weighted_vote"):
        self.strategy = strategy
        self.strategy_func = get_strategy(strategy)
        self.experts = load_expert_configs()
        for i, exp in enumerate(self.experts, 1):
            exp['id'] = i
        
        self.llm = get_llm()
        if self.llm is None:
            logger.error("❌ 无法获取 LLM 实例")
    
    async def execute(self, question: str) -> Dict[str, Any]:
        """执行议会收敛 - 只生成可执行JSON"""
        logger.info(f"🏛️ 议会执行: {question[:50]}...")
        
        if self.llm is None:
            return {
                "final_decision": "error",
                "confidence_score": 0,
                "error": "LLM 不可用",
                "executable_plan": ["系统错误: LLM 未初始化"]
            }
        
        loop = asyncio.get_event_loop()
        tasks = []
        for expert in self.experts:
            tasks.append(loop.run_in_executor(
                None,
                _call_expert,
                self.llm,
                expert,
                question
            ))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_responses = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                processed_responses.append({
                    "expert_id": self.experts[i].get('id', i+1),
                    "expert_name": self.experts[i].get('name', f'专家{i+1}'),
                    "raw_text": str(resp),
                    "parsed_json": {"choice": "error", "confidence": 0},
                    "valid_json": False,
                    "confidence": 0
                })
            else:
                processed_responses.append(resp)
        
        valid_count = sum(1 for r in processed_responses if r.get('valid_json'))
        logger.info(f"✅ 收到 {valid_count}/6 个有效 JSON 响应")
        
        result = self.strategy_func(processed_responses)
        
        result.update({
            "convergence_metadata": {
                "strategy": self.strategy,
                "expert_count": len(processed_responses),
                "valid_responses": valid_count,
                "timestamp": datetime.utcnow().isoformat(),
                "question": question
            },
            "expert_details": [
                {
                    "id": r.get('expert_id'),
                    "name": r.get('expert_name'),
                    "valid": r.get('valid_json', False),
                    "choice": r.get('parsed_json', {}).get('choice', 'N/A'),
                    "confidence": r.get('confidence', 0)
                }
                for r in processed_responses
            ]
        })
        
        # 生成可执行JSON
        result["executable"] = generate_executable_json(result)
        
        logger.info(f"✅ 最终决策: {result['final_decision']}")
        return result
    
    def execute_sync(self, question: str) -> Dict[str, Any]:
        """同步执行"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.execute(question))
        finally:
            loop.close()

# ==================== 7. 存储执行JSON ====================
def save_execution_record(executable: Dict) -> str:
    """保存执行JSON到 discussions 目录"""
    try:
        discussions_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "discussions"
        )
        os.makedirs(discussions_dir, exist_ok=True)
        
        filename = f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(discussions_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(executable, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 执行JSON已保存: {filepath}")
        return filename
        
    except Exception as e:
        logger.error(f"保存执行JSON失败: {e}")
        return None

# ==================== 8. 对外接口 ====================
def parliament_execute(question: str, strategy: str = "weighted_vote") -> Dict[str, Any]:
    """执行议会收敛（同步接口）- 只生成可执行JSON"""
    executor = ParliamentExecutor(strategy=strategy)
    result = executor.execute_sync(question)
    
    # 只返回可执行JSON，不执行
    executable = generate_executable_json(result)
    
    # 保存执行JSON
    #filename = save_execution_record(executable)
    
    return {
        "status": "success",
        "executable": executable,
        "json_file": filename
    }


def parliament_execute_json(question: str, strategy: str = "weighted_vote") -> str:
    """执行议会收敛，返回 JSON 字符串"""
    result = parliament_execute(question, strategy)
    return json.dumps(result, ensure_ascii=False, indent=2)

# ==================== 9. 异步接口 ====================
async def parliament_execute_async(question: str, strategy: str = "weighted_vote") -> Dict[str, Any]:
    """
    异步执行议会收敛 - 只生成可执行JSON，不执行
    """
    executor = ParliamentExecutor(strategy=strategy)
    result = await executor.execute(question)
    
    executable = generate_executable_json(result)
    filename = save_execution_record(executable)
    
    # 生成 events（简洁版本，不包含三轮讨论）
    events = []
    events.append({
        "type": "start",
        "message": f"⚡ 议会执行启动: {question}"
    })
    events.append({
        "type": "complete",
        "executable": executable,
        "json_file": filename,
        "status": "pending_review"
    })
    
    return {
        "status": "success",
        "events": events,
        "executable": executable,
        "json_file": filename
    }


def parliament_execute_with_json(question: str, strategy: str = "weighted_vote") -> str:
    """执行议会收敛并返回 JSON 字符串（兼容接口）"""
    return parliament_execute_json(question, strategy)


def get_available_strategies() -> List[str]:
    """获取所有可用策略"""
    return list(STRATEGIES.keys())


def set_strategy(name: str):
    """设置全局默认策略（兼容接口）"""
    if name not in STRATEGIES:
        raise ValueError(f"未知策略: {name}，可用: {list(STRATEGIES.keys())}")
    global _default_strategy
    _default_strategy = name


_default_strategy = "weighted_vote"


# ==================== 10. 兼容类 ====================
class ExecutableJSONGenerator:
    """可执行JSON生成器（兼容类）"""
    
    @staticmethod
    def generate(result: Dict) -> Dict:
        return generate_executable_json(result)
    
    @staticmethod
    def to_json_string(result: Dict, indent: int = 2) -> str:
        executable = generate_executable_json(result)
        return json.dumps(executable, ensure_ascii=False, indent=indent)
    
    @staticmethod
    def save_to_file(result: Dict, filename: Optional[str] = None) -> str:
        if filename is None:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"parliament_exec_{timestamp}.json"
        
        json_str = ExecutableJSONGenerator.to_json_string(result)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        logger.info(f"💾 可执行JSON已保存到: {filename}")
        return filename


# ==================== 11. MCP 执行（由 Harness 调用） ====================
async def execute_mcp_from_json(executable: Dict) -> Dict[str, Any]:
    """
    由 Harness 调用，根据可执行JSON执行MCP技能
    """
    from .parliament_skill_mapper import mcp_call
    
    decision = executable.get("decision", "")
    params = executable.get("executable", {}).get("params", {})
    
    # 根据decision映射到技能
    skill_map = {
        "清理缓存": "optimize_system",
        "系统优化": "optimize_system",
        "封锁IP": "block_ip",
        "验证IP": "validate_ip",
        "执行脚本": "execute_shell_script",
        "设置定时任务": "setup_cron_job",
    }
    
    skill = None
    for key, value in skill_map.items():
        if key in decision:
            skill = value
            break
    
    if not skill:
        return {"status": "error", "message": f"未知决策: {decision}"}
    
    return await mcp_call(skill, **params)


# ==================== 12. 测试入口 ====================
if __name__ == "__main__":
    result = parliament_execute("清理docker构建缓存")
    print(json.dumps(result, ensure_ascii=False, indent=2))
