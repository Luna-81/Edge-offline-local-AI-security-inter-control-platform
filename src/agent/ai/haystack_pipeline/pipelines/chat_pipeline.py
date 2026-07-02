"""
ChatPipeline - 4角色对话 Pipeline（使用 LlamaGenerator）
支持：传统 Pipeline + 圆桌会议模式（@单列 + 1234总结）
"""
import logging
from typing import Dict, Any, Optional

from haystack import Pipeline
from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack.components.builders import PromptBuilder
from haystack.utils import ComponentDevice

import sys
import os
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ✅ 确保导入正确
from roundtable.experts import expert_say, get_engine
from roundtable.harness_qvk import HarnessQVK
from roundtable.session_manager import SessionManager

logger = logging.getLogger("Roundtable.Say")

# ✅ 调试：确认 get_engine 是否可用
logger.info(f"🔍 get_engine 导入成功: {get_engine}")

from haystack_pipeline.components.role_retriever import RoleRetriever
from haystack_pipeline.components.llama_generator import LlamaGenerator
from haystack_pipeline.components.role_retriever import format_role_documents

# ✅ 导入圆桌会议模块
from roundtable.roundtable_say import roundtable_say
from roundtable.experts import init_expert_engine, get_engine


logger = logging.getLogger("Haystack.ChatPipeline")

# ============================================================
# 配置
# ============================================================
EMBEDDING_MODEL_PATH = "/home/rick/knowpasser/src/agent/ai/models/bge-small-zh-v1.5"
LLM_MODEL_PATH = "/home/rick/knowpasser/src/agent/ai/models/gemma-2-2b-it-Q4_K_M.gguf"
MAX_OUTPUT_TOKENS = 512
MAX_TOTAL_TOKENS = 4096
TEMPERATURE = 0.3

# ============================================================
# Prompt 模板
# ============================================================
CHAT_TEMPLATE = """
<start_of_turn>user
你是一个专业的网络安全与系统专家（AegisNet 核心引擎）。

{% if role_context %}
### 多角色交叉分析（4个专家视角）
{{ role_context }}
{% endif %}

### 用户问题
{{ query }}

[回答要求]
1. 优先使用【安全知识库】中的建议措施。
2. 如果多个角色视角有相关内容，请综合给出更全面的回答。
3. 提供可执行的命令示例。
4. 严禁回答'暂未录入'。保持专业性。
5. 直接给出完整、详尽的回答。
<end_of_turn>
<start_of_turn>model
"""


# ============================================================
# 创建 Pipeline
# ============================================================
def create_chat_pipeline(
    top_k: int = 3,
    use_gpu: bool = True,
    llm_instance=None,
) -> Pipeline:
    """创建 4角色聊天 Pipeline"""
    logger.info("🚀 创建 4角色聊天 Pipeline...")
    
    pipeline = Pipeline()
    
    if use_gpu:
        device = ComponentDevice.from_str("cuda:0")
    else:
        device = ComponentDevice.from_str("cpu")
    logger.info(f"📱 使用设备: {device}")
    
    pipeline.add_component(
        "embedder",
        SentenceTransformersTextEmbedder(
            model=EMBEDDING_MODEL_PATH,
            device=device,
            normalize_embeddings=True
        )
    )
    
    pipeline.add_component(
        "retriever",
        RoleRetriever(top_k=top_k)
    )
    
    pipeline.add_component(
        "prompt_builder",
        PromptBuilder(template=CHAT_TEMPLATE)
    )
    
    pipeline.add_component(
        "generator",
        LlamaGenerator(
            llm_instance=llm_instance,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
        )
    )
    
    pipeline.connect("embedder.embedding", "retriever.query_embedding")
    pipeline.connect("prompt_builder.prompt", "generator.prompt")
    
    logger.info("✅ ChatPipeline 创建完成")
    return pipeline


# ============================================================
# 简化的对话入口（集成圆桌会议）
# ============================================================
class HaystackTalker:
    def __init__(
        self, 
        top_k: int = 3, 
        use_gpu: bool = True,
        llm_instance=None,           # LlamaGenerator 包装器（Pipeline 用）
        raw_llm_instance=None,       # llama-cpp 原始实例（圆桌会议用）
        encoder_instance=None,
        lock=None
    ):
        logger.info("🔄 HaystackTalker 初始化...")
        logger.info(f"🔍 raw_llm_instance 是否为 None: {raw_llm_instance is None}")
        logger.info(f"🔍 raw_llm_instance 类型: {type(raw_llm_instance) if raw_llm_instance else 'None'}")
        self.top_k = top_k
        self.llm_instance = llm_instance
        self.encoder_instance = encoder_instance
        self.lock = lock
        self._history = {}
        
        # ✅ 初始化圆桌会议专家引擎（使用 raw_llm_instance）
        if raw_llm_instance is not None:
            try:
                logger.info(f"🔧 正在初始化圆桌会议，raw_llm_instance 类型: {type(raw_llm_instance)}")
                init_expert_engine(llm_instance=raw_llm_instance)
                logger.info("✅ Roundtable ExpertEngine 已初始化（使用原始 llama 实例）")
            except Exception as e:
                logger.warning(f"⚠️ 圆桌会议初始化失败: {e}")
        else:
            logger.warning("⚠️ raw_llm_instance 为 None，圆桌会议将不可用")

        # 方案：如果 llm_instance 是 LlamaGenerator，提取内部的 llm
        if llm_instance is not None and hasattr(llm_instance, 'llm'):
            pipeline_llm = llm_instance.llm  # 提取 llama-cpp 实例
            logger.info("✅ 从 LlamaGenerator 提取原始 llama 实例用于 Pipeline")
        else:
            pipeline_llm = llm_instance
        
        self.pipeline = create_chat_pipeline(
            top_k=top_k,
            use_gpu=use_gpu,
            llm_instance=pipeline_llm  # ← 使用提取后的 llama-cpp 实例
        )
        logger.info("✅ HaystackTalker 初始化完成")
    
    async def talk(
        self,
        username: str,
        question: str,
        history: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        执行对话 - 智能路由：
        - 包含 @ 或默认 → 圆桌会议模式（@单列 + 1234总结）
        - 以 /legacy 开头 → 传统 Pipeline 模式
        """
        try:
            # ✅ 智能路由：默认使用圆桌会议，除非明确指定传统模式
            use_roundtable = True
            
            # 如果用户明确要求传统模式
            if question.startswith("/legacy"):
                question = question[7:].strip()
                use_roundtable = False
            
            # 如果 llm_instance 为空，回退到传统模式
            if self.llm_instance is None:
                use_roundtable = False
                logger.warning("⚠️ llm_instance 为空，回退到传统 Pipeline 模式")
            
            if use_roundtable:
                # 🎯 使用圆桌会议模式（@单列 + 1234轮答 + 总结）
                logger.info(f"🔵 使用圆桌会议模式: {username} -> {question[:30]}...")
                answer = await roundtable_say(username, question)
                return {
                    "answer": answer,
                    "total_chunks": 0,
                    "loops": 1,
                    "source": "roundtable"
                }
            
            else:
                # 📚 传统 Pipeline 模式（4角色检索 + 生成）
                logger.info(f"📚 使用传统 Pipeline 模式: {username}")
                
                from haystack_pipeline.components.role_retriever import RoleRetriever
                retriever = RoleRetriever(top_k=self.top_k)
                retrieval_result = retriever.run(query=question)
                
                documents = retrieval_result.get("documents", [])
                role_context = format_role_documents(documents)
                total_chunks = retrieval_result.get("total_chunks", 0)
                
                result = self.pipeline.run(
                    {
                        "embedder": {"text": question},
                        "retriever": {"query": question},
                        "prompt_builder": {
                            "query": question,
                            "role_context": role_context
                        }
                    }
                )
                
                answer = result.get("generator", {}).get("replies", [""])[0]
                
                return {
                    "answer": answer,
                    "total_chunks": total_chunks,
                    "loops": 1,
                    "source": "haystack_pipeline"
                }
            
        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            return {
                "answer": f"抱歉，处理请求时出错: {e}",
                "total_chunks": 0,
                "loops": 0,
                "source": "error"
            }


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    import asyncio
    import gc
    
    async def test():
        print("="*60)
        print("测试 HaystackTalker（圆桌会议集成）")
        print("="*60)
        
        # ✅ 加载模型
        from haystack_pipeline.components.llama_generator import LlamaGenerator
        from llama_cpp import Llama
        
        print("🔧 加载模型...")
        llama_instance = Llama(
            model_path=LLM_MODEL_PATH,
            n_ctx=4096,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False,
        )
        
        # ✅ 创建 LlamaGenerator 包装器（传入 llama_instance）
        llm_generator = LlamaGenerator(
            llm_instance=llama_instance,
            max_tokens=512,
            temperature=0.3,
        )
        
        # ✅ 创建 Talker（传入 llm_generator）
        talker = HaystackTalker(
            top_k=3,
            use_gpu=False,
            llm_instance=llm_generator,
            raw_llm_instance=llama_instance,
        )
        
        # 测试1: @技术 单列模式
        print("\n" + "="*60)
        print("测试1: @技术 单列模式")
        print("="*60)
        result = await talker.talk("test_user", "@技术 如何优化SQL查询性能？")
        print(f"来源: {result['source']}")
        print(f"回复:\n{result['answer'][:500]}...")
        
        # 测试2: 综合模式（无@）
        print("\n" + "="*60)
        print("测试2: 综合模式（无@，1234轮答+总结）")
        print("="*60)
        result = await talker.talk("test_user", "什么是向量数据库？")
        print(f"来源: {result['source']}")
        print(f"回复:\n{result['answer'][:500]}...")
        
        # 测试3: 传统模式（/legacy 前缀）
        print("\n" + "="*60)
        print("测试3: 传统 Pipeline 模式（/legacy 前缀）")
        print("="*60)
        result = await talker.talk("test_user", "/legacy 什么是LLM？")
        print(f"来源: {result['source']}")
        print(f"回复:\n{result['answer'][:500]}...")
        
        # ✅ 返回 llama_instance 以便外部清理
        return llama_instance
    
    # ✅ 运行测试并获取模型实例
    print("🚀 开始运行测试...")
    llama_instance = asyncio.run(test())
    
    # ✅ 在 asyncio.run() 之外清理资源
    print("\n🔧 释放模型资源...")
    try:
        # 1. 先关闭模型（正确的方式）
        if llama_instance is not None and hasattr(llama_instance, 'close'):
            try:
                llama_instance.close()
                print("✅ 模型 close() 成功")
            except Exception as e:
                print(f"⚠️ close() 失败: {e}")
        
        # 2. 删除引用
        del llama_instance
        
        # 3. 强制垃圾回收
        gc.collect()
        print("✅ 模型资源已释放")
        
    except Exception as e:
        print(f"⚠️ 清理资源时出错: {e}")
