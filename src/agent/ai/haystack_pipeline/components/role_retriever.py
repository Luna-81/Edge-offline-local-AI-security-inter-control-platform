"""
RoleRetriever - Haystack 组件
将 4角色检索 封装为 Haystack 可复用组件
"""
import logging
import json
import asyncio
import concurrent.futures
import numpy as np
from typing import List, Dict, Any, Optional
from haystack import Document, component

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retriever_4role import multi_role_retrieve, format_role_results, ROLE_CONFIG

logger = logging.getLogger("Haystack.RoleRetriever")

# ============================================================
# 角色权重配置（从 roles.yaml 加载）
# ============================================================
def load_role_weights():
    """从 roles.yaml 加载权重"""
    try:
        roles = ROLE_CONFIG.get("roles", [])
        weights = {}
        for role in roles:
            weights[role["name"]] = {
                "display_name": role.get("display_name", role["name"]),
                "description": role.get("description", ""),
                "weight": role["weight"]
            }
        return weights
    except Exception as e:
        logger.error(f"加载角色权重失败: {e}")
        return {
            "config_expert": {
                "display_name": "配置专家",
                "description": "精确匹配命令、参数、配置文件",
                "weight": [0.7, 0.6, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1]
            },
            "architect": {
                "display_name": "架构师",
                "description": "理解系统设计逻辑、因果链路",
                "weight": [0.1, 0.1, 0.2, 0.7, 0.6, 0.2, 0.1, 0.1]
            },
            "intent_classifier": {
                "display_name": "意图识别官",
                "description": "判断用户意图、主题分类",
                "weight": [0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.7, 0.6]
            },
            "security_auditor": {
                "display_name": "安全审计官",
                "description": "审查异常行为、安全威胁",
                "weight": [0.2, 0.2, 0.6, 0.2, 0.2, 0.6, 0.2, 0.2]
            }
        }


@component
class RoleRetriever:
    """
    4角色检索器 - Haystack 组件
    
    输入: query (str), query_embedding (Optional[List[float]])
    输出: documents (List[Document]), role_results (Dict)
    """
    
    def __init__(
        self,
        top_k: int = 3,
        include_scores: bool = True,
        role_weights: Optional[Dict] = None
    ):
        self.top_k = top_k
        self.include_scores = include_scores
        self.role_weights = role_weights or load_role_weights()
        logger.info(f"✅ RoleRetriever 初始化: top_k={top_k}, 角色数={len(self.role_weights)}")
    
    @component.output_types(
        documents=List[Document],
        role_results=Dict,
        total_chunks=int
    )
    def run(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None
    ):
        """
        执行4角色检索 - 同步版本（支持在事件循环中调用）
        """
        logger.info(f"🔍 RoleRetriever 开始检索: {query[:30]}...")
        
        try:
            # ✅ 修复：使用线程池执行异步任务
            def _run_async():
                return asyncio.run(multi_role_retrieve(query))
            
            # 使用线程池执行，避免事件循环冲突
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_async)
                role_results = future.result(timeout=60)  # 60秒超时
            
            if not role_results:
                logger.info("📭 4角色检索无结果")
                return {
                    "documents": [],
                    "role_results": {},
                    "total_chunks": 0
                }
            
            # 转换为 Haystack Document 格式
            documents = []
            total_chunks = 0
            
            for role_name, chunks in role_results.items():
                role_info = self.role_weights.get(role_name, {})
                display_name = role_info.get("display_name", role_name)
                
                for chunk_text, score, metadata in chunks:
                    if len(chunk_text) > 500:
                        chunk_text = chunk_text[:500] + "..."
                    
                    doc = Document(
                        content=chunk_text,
                        meta={
                            "role": role_name,
                            "role_display": display_name,
                            "score": score,
                            "source": metadata.get("source", "doc_chunks"),
                            "chunk_id": metadata.get("chunk_id", ""),
                            "is_4role": True
                        },
                        score=score
                    )
                    documents.append(doc)
                    total_chunks += 1
            
            logger.info(f"✅ RoleRetriever 完成: {total_chunks} 个Chunk")
            
            return {
                "documents": documents,
                "role_results": role_results,
                "total_chunks": total_chunks
            }
            
        except concurrent.futures.TimeoutError:
            logger.error("❌ RoleRetriever 超时 (60秒)")
            return {"documents": [], "role_results": {}, "total_chunks": 0}
        except Exception as e:
            logger.error(f"❌ RoleRetriever 失败: {e}", exc_info=True)
            return {
                "documents": [],
                "role_results": {},
                "total_chunks": 0
            }


# ============================================================
# 角色结果格式化（用于 Prompt）
# ============================================================
def format_role_documents(documents: List[Document]) -> str:
    """将角色文档格式化为文本"""
    if not documents:
        return ""
    
    grouped = {}
    for doc in documents:
        role = doc.meta.get("role_display", doc.meta.get("role", "未知"))
        if role not in grouped:
            grouped[role] = []
        grouped[role].append(doc)
    
    parts = []
    for role, docs in grouped.items():
        parts.append(f"\n【{role}】")
        for i, doc in enumerate(docs, 1):
            score = doc.meta.get("score", 0)
            parts.append(f"  {i}. {doc.content} (相关度: {score:.4f})")
    
    return "\n".join(parts)


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    import asyncio
    
    async def test():
        retriever = RoleRetriever(top_k=3)
        result = retriever.run(query="什么是LLM模型？")
        print(f"结果: {result['total_chunks']} 个Chunk")
        for doc in result['documents']:
            print(f"  [{doc.meta['role_display']}] {doc.content[:50]}...")
    
    asyncio.run(test())
