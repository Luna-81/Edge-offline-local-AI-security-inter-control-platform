"""
LlamaGenerator - 使用 local_brain 的共享 LLM 实例
"""
import logging
import asyncio
from typing import List
from haystack import component

logger = logging.getLogger("Haystack.LlamaGenerator")

@component
class LlamaGenerator:
    """
    使用 local_brain 已有的 LLM 实例（带锁）
    """
    
    def __init__(
        self, 
        llm_instance=None, 
        lock=None,           # ← 传入锁
        max_tokens: int = 512,
        temperature: float = 0.3,
        top_p: float = 0.45,
        top_k: int = 30,
        repeat_penalty: float = 1.1,
    ):
        self.llm = llm_instance
        self.lock = lock or asyncio.Lock()  # 如果没有锁，创建一个
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repeat_penalty = repeat_penalty
        
        if self.llm is None:
            logger.warning("⚠️ LLM 实例为 None，生成将失败")
        else:
            logger.info("✅ 使用共享 LLM 实例（带锁保护）")
    
    @component.output_types(replies=List[str])
    def run(self, prompt: str):
        """执行生成（使用锁保护）"""
        if self.llm is None:
            return {"replies": ["LLM 未初始化"]}
        
        # 使用锁保护共享模型
        try:
            # 在同步组件中使用 asyncio 锁需要特殊处理
            # 这里使用一个简单的线程锁
            import threading
            if not hasattr(self, '_thread_lock'):
                self._thread_lock = threading.Lock()
            
            with self._thread_lock:
                response = self.llm(
                    prompt,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    repeat_penalty=self.repeat_penalty,
                    stop=["<end_of_turn>", "<start_of_turn>"],
                    echo=False,
                )
                text = response["choices"][0]["text"].strip()
                return {"replies": [text]}
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            return {"replies": [f"生成失败: {e}"]}
