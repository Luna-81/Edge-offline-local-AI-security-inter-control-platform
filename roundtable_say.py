import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import roundtable.experts as experts_module
from roundtable.experts import expert_say, get_engine
from roundtable.harness_qvk import HarnessQVK
from roundtable.session_manager import SessionManager
from roundtable.parliament_executor import parliament_execute, parliament_execute_json

# 🆕 新增导入 - 议会执行模式
from roundtable.parliament_executor import parliament_execute_async, ExecutableJSONGenerator

logger = logging.getLogger("Roundtable.Say")

_session_manager = SessionManager()
logger.info(f"🔍 experts_module 导入成功: {experts_module}")

async def _retrieve_knowledge(question: str, top_k: int = 5) -> str:
    """从本地知识库检索相关内容"""
    try:
        # ✅ 尝试多种导入方式
        try:
            from AegisNet.Talker import AegisTalker
            talker = AegisTalker()
            results = talker.retrieve(question, top_k=top_k)
        except ImportError:
            # 如果 AegisNet 不可用，尝试使用 memory_vault
            try:
                import sys
                sys.path.insert(0, '/home/rick/knowpasser/src/agent/ai')
                from memory_vault import memory_vault
                results = await memory_vault.search(question)
                if isinstance(results, dict):
                    results = [results]
            except:
                return "（检索服务不可用）"
        
        if results:
            formatted = []
            for i, r in enumerate(results, 1):
                text = r.get('text', '')[:300]
                score = r.get('score', 0)
                formatted.append(f"[{i}] (相关度: {score:.2f})\n{text}")
            return "\n\n".join(formatted)
        else:
            return "（未检索到相关知识）"
            
    except Exception as e:
        logger.warning(f"检索失败: {e}")
        return "（检索服务不可用）"


# ✅ 新增：确保引擎已初始化的函数（懒加载）
def _ensure_engine() -> bool:
    """确保引擎已初始化（懒加载）"""
    if experts_module._shared_engine is not None:
        return True
    
    # 尝试从 local_brain 获取 llm
    try:
        import local_brain
        if hasattr(local_brain, 'llm') and local_brain.llm is not None:
            from roundtable.experts import ExpertEngine
            logger.info("🔧 [roundtable] 懒加载引擎（使用 local_brain 的 LLM）...")
            experts_module._shared_engine = ExpertEngine(llm_instance=local_brain.llm)
            if experts_module._shared_engine is not None:
                logger.info("✅ [roundtable] 引擎懒加载成功")
                return True
            else:
                logger.error("❌ [roundtable] 引擎懒加载失败")
                return False
        else:
            logger.error("❌ [roundtable] local_brain.llm 为 None，无法初始化")
            return False
    except Exception as e:
        logger.error(f"❌ [roundtable] 懒加载异常: {e}")
        return False


# 🆕 新增：议会执行模式处理函数
async def _parliament_execute_mode(question: str, strategy: str = "weighted_vote") -> str:
    """议会执行模式 - 返回可执行JSON"""
    logger.info(f"🏛️ 进入议会执行模式: {question[:50]}...")
    
    try:
        if not _ensure_engine():
            return "错误：引擎初始化失败，请检查系统状态"
        
        result = await parliament_execute_async(question, strategy)
        
        summary = f"""
╔══════════════════════════════════════════════════════════════╗
║  🏛️  6议会执行模式 - 决策报告                              ║
╠══════════════════════════════════════════════════════════════╣
║  📌 问题: {question[:60]}{'...' if len(question) > 60 else ''}
║  ✅ 最终决策: {result['final_decision']}
║  📊 置信度: {result['confidence_score']:.2%}
║  📋 策略: {result.get('method', 'unknown')}
║  👥 有效专家: {result['convergence_metadata']['valid_responses']}/6
╠══════════════════════════════════════════════════════════════╣
║  📋 执行计划:                                              ║
"""
        for step in result.get('executable_plan', []):
            summary += f"║    • {step[:50]}{'...' if len(step) > 50 else ''}\n"
        
        summary += "╠══════════════════════════════════════════════════════════════╣\n"
        summary += "║  📄 可执行JSON (详见下方)                                   ║\n"
        summary += "╚══════════════════════════════════════════════════════════════╝\n\n"
        summary += ExecutableJSONGenerator.to_json_string(result)
        
        return summary
        
    except Exception as e:
        logger.error(f"议会执行模式失败: {e}")
        return f"❌ 议会执行失败: {str(e)}"


async def roundtable_say(username: str, user_input: str) -> str:
    """圆桌会议入口"""
    logger.info(f"🔵 用户 {username}: {user_input[:50]}...")
    
    # ============================================================
    # 🆕 0. 检测 /exec 命令 → JSON收敛执行模式（优先检测）
    # ============================================================
    if user_input.strip().startswith("/exec"):
        question = user_input.replace("/exec", "", 1).strip()
        if not question:
            return "📋 请提供要决策的问题：\n   /exec 我们应该选择哪个方案？"
        
        # 检测策略参数
        strategy = "weighted_vote"
        if " --strategy " in question:
            parts = question.split(" --strategy ")
            question = parts[0].strip()
            strategy = parts[1].strip().split()[0] if parts[1] else "weighted_vote"
            if strategy not in ["weighted_vote", "consensus", "statistical"]:
                strategy = "weighted_vote"
        
        return await _parliament_execute_mode(question, strategy)
    
    # 🆕 检测 /help
    if user_input.strip().startswith("/help"):
        return """
📋 圆桌会议命令帮助:

  /exec {问题}              - 议会执行模式，返回可执行JSON决策
  /exec {问题} --strategy   - 指定策略 (weighted_vote|consensus|statistical)
  @{专家ID} {问题}          - 单列模式，咨询指定专家 (1-6)
  /help                     - 显示此帮助

示例:
  /exec 我们应该选择AWS还是Azure？
  /exec 系统架构如何优化？ --strategy consensus
  @3 数据库应该用PostgreSQL还是MongoDB？
"""
    
    # ============================================================
    # 1. 单列模式检测退出（原有逻辑，不变）
    # ============================================================
    session = _session_manager.get_session(username)
    logger.info(f"🔍 [roundtable_say] session.mode={session.mode}")
    
    if session.mode == "single":
        if _session_manager.detect_exit(user_input):
            exit_msg = _session_manager.exit_single_mode(username)
            return exit_msg
    
    # ============================================================
    # 2. 检测 @ 切换 → 进入单列模式（原有逻辑，不变）
    # ============================================================
    expert_id = _session_manager.detect_expert_switch(user_input)
    if expert_id is not None:
        _session_manager.enter_single_mode(username, expert_id)
        logger.info(f"🔵 进入单列模式，专家: {expert_id}")
        return await _single_expert_reply(expert_id, user_input)
    
    # ============================================================
    # 3. 综合模式（原有逻辑，不变）
    # ============================================================
    return await _full_mode_reply(user_input)


async def _single_expert_reply(expert_id: int, user_input: str) -> str:
    try:
        if not _ensure_engine():
            return "错误：引擎初始化失败，请检查系统状态"
        return await experts_module.expert_say(expert_id, user_input)
    except Exception as e:
        logger.error(f"单列专家 {expert_id} 失败: {e}")
        return f"专家回复失败: {e}"


async def _full_mode_reply(user_input: str) -> str:
    if not _ensure_engine():
        return "错误：引擎初始化失败，请检查系统状态"
    
    # 🆕 1. 检索本地知识库
    logger.info(f"🔍 检索本地知识库: {user_input[:50]}...")
    knowledge = await _retrieve_knowledge(user_input, top_k=5)
    logger.info(f"📚 检索完成，知识长度: {len(knowledge)} 字符")
    
    # 2. 并发收集6议会意见（带知识库上下文）
    tasks = [_expert_say_with_knowledge(i, user_input, knowledge) for i in range(1, 7)]
    replies_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    replies = {}
    for i, reply in enumerate(replies_list, start=1):
        if isinstance(reply, Exception):
            replies[i] = f"[专家{i}出错] {str(reply)}"
        else:
            replies[i] = reply
    
    harness = HarnessQVK()
    weighted_prompt = harness.build_weighted_prompt(user_input, replies)
    
    engine = experts_module.get_engine()
    logger.info(f"🔍 _full_mode_reply: engine = {engine}, type = {type(engine)}")

    if engine is None:
        return "错误：专家引擎未初始化"
    
    if engine.llm is None:
        return "错误：LLM 不可用"
    
    if not callable(engine.llm):
        return f"错误：LLM 不可调用 (类型: {type(engine.llm)})"
    
    # 🆕 在总结提示中包含检索到的知识
    summary_prompt = f"""<start_of_turn>user
你是一个总结专家。综合以下专家的意见，给出最终回答。

### 参考知识（从知识库检索）
{knowledge}

### 专家意见（已加权）
{weighted_prompt}

要求：
1. 优先采信权重高的专家意见
2. 如果意见冲突，取更安全/保守的方案
3. 结合参考知识，确保回答准确
4. 输出直接面向用户，专业但易懂
<end_of_turn>
<start_of_turn>model
"""
    
    loop = asyncio.get_event_loop()
    
    try:
        result = await loop.run_in_executor(
            None,
            lambda: engine.llm(
                summary_prompt,
                max_tokens=512,
                temperature=0.3,
                stop=["<end_of_turn>", "<start_of_turn>"],
                echo=False,
            )
        )
        final_reply = result["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"总结生成失败: {e}")
        return f"总结生成失败: {e}"
    
    logger.info(f"📊 权重: {harness.weigh_replies(user_input, replies)}")
    
    # 🆕 返回时带上检索来源标识
    if knowledge and "（未检索到" not in knowledge and "不可用" not in knowledge:
        final_reply += f"\n\n📚 *基于本地知识库检索增强*"
    
    return final_reply


# ==================== 新增：专家调用（带知识库） ====================
async def _expert_say_with_knowledge(expert_id: int, user_input: str, knowledge: str) -> str:
    """专家调用 - 带知识库上下文"""
    try:
        if not _ensure_engine():
            return "错误：引擎初始化失败"
        
        engine = experts_module.get_engine()
        if engine is None:
            return "错误：引擎未初始化"
        
        role_config = engine.mapper.get_role_by_id(expert_id)
        if not role_config:
            return f"[错误] 未找到专家 ID: {expert_id}"
        
        # 🆕 构建带知识库的提示
        prompt = f"""<start_of_turn>user
你是一个专业专家，请严格遵守以下 System Prompt。

### System Prompt
{role_config["system_prompt"]}

### 参考知识（从本地知识库检索到的相关内容）
{knowledge}

### 用户问题
{user_input}

请结合参考知识，给出专业回答。如果知识库信息与你的判断冲突，请说明。
保持简洁、专业。
<end_of_turn>
<start_of_turn>model
"""
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, engine._generate, prompt)
        
    except Exception as e:
        logger.error(f"专家 {expert_id} 调用失败: {e}")
        return f"专家回复失败: {e}"
