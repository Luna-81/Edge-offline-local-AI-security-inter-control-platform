

import sys
import os
import numpy as np
from typing import List, Dict
import jieba

# ✅ 添加父目录到路径（支持绝对导入）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roundtable.role_mapper import RoleMapper


class HarnessQVK:
    def __init__(self):
        self.mapper = RoleMapper()
        self.profile_weight = 0.4   # 可以从 config.yaml 读取
        self.reply_weight = 0.6
        self.min_threshold = 0.05
        
        # 从 mapper 构建专家画像
        self.expert_profiles = self._build_expert_profiles()
    
    def _build_expert_profiles(self):
        profiles = {}
        all_roles = self.mapper.get_all_roles()
        for role in all_roles:
            profiles[role["role_id"]] = {
                "name": role["config_name"],
                "keywords": role["keywords"],
                "weight": role["roles_weight"],  # 8×64 向量权重
            }
        return profiles
    
    def _extract_keywords(self, text: str) -> List[str]:
        words = jieba.lcut(text)
        return [w for w in words if len(w) > 1]
    
    def _compute_similarity(self, user_keywords: List[str], expert_keywords: List[str]) -> float:
        if not user_keywords or not expert_keywords:
            return 0.0
        intersection = set(user_keywords) & set(expert_keywords)
        union = set(user_keywords) | set(expert_keywords)
        return len(intersection) / len(union) if union else 0.0
    
    def weigh_replies(self, user_input: str, replies: Dict[int, str]) -> Dict[int, float]:
        user_keywords = self._extract_keywords(user_input)
        weights = {}
        
        for expert_id, reply in replies.items():
            reply_keywords = self._extract_keywords(reply)
            profile_sim = self._compute_similarity(
                user_keywords, 
                self.expert_profiles[expert_id]["keywords"]
            )
            reply_sim = self._compute_similarity(user_keywords, reply_keywords)
            score = self.profile_weight * profile_sim + self.reply_weight * reply_sim
            weights[expert_id] = score
        
        exp_scores = np.exp(list(weights.values()))
        softmax_weights = exp_scores / np.sum(exp_scores)
        return {eid: softmax_weights[i] for i, eid in enumerate(weights.keys())}
    
    def build_weighted_prompt(self, user_input: str, replies: Dict[int, str]) -> str:
        weights = self.weigh_replies(user_input, replies)
        sorted_experts = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        
        prompt = f"用户问题：{user_input}\n\n专家意见（按重要性排序）：\n"
        for expert_id, weight in sorted_experts:
            if weight < self.min_threshold:
                continue
            name = self.expert_profiles[expert_id]["name"]
            reply = replies[expert_id]
            prompt += f"\n【{name}】（权重 {weight:.2f}）：\n{reply}\n"
        
        prompt += "\n请综合以上意见，输出最终回答，优先采信权重高的专家意见。"
        return prompt
