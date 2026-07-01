

import logging
import os
import yaml
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("Roundtable.Session")

@dataclass
class Session:
    """单个用户的会话状态"""
    mode: str = "full"          # "full" | "single"
    active_expert: Optional[int] = None  # 1-4
    history: list = field(default_factory=list)
    expert_history: Dict[int, list] = field(default_factory=dict)

class SessionManager:
    """
    会话管理器：管理每个用户的模式切换
    """
    
    def __init__(self, config_path: str = None):
        self._sessions: Dict[str, Session] = {}
        
        # ✅ 从 config.yaml 加载配置
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "config.yaml"
            )
        
        self._load_config(config_path)
    
    def _load_config(self, config_path: str):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        
            single_mode = config.get('single_mode', {})
            self.single_enabled = single_mode.get('enabled', True)
            self._exit_keywords = single_mode.get('exit_keywords', ["/exit"])
        
            logger.info(f"✅ 从 config.yaml 加载退出关键词: {self._exit_keywords}")
        
        except Exception as e:
            logger.warning(f"⚠️ 加载 config.yaml 失败: {e}，使用默认配置")
            self.single_enabled = True
            self._exit_keywords = ["/exit"]

    def detect_exit(self, text: str) -> bool:
        """检测用户是否说了退出词"""
        if not text:
            return False
    
        text_clean = text.strip().lower()
    
    #  明确命令：/exit
        if text_clean == "/exit":
            logger.info(f"✅ [退出检测] 命令退出: '{text}'")
            return True
        return False
    
    
    def get_session(self, username: str) -> Session:
        """获取或创建用户会话"""
        if username not in self._sessions:
            self._sessions[username] = Session()
        return self._sessions[username]
    
    def detect_expert_switch(self, text: str) -> Optional[int]:
        """
        检测用户是否 @ 了某个专家
        返回: 1-4 表示专家ID，None 表示没有
        """
        # ✅ 修正映射：匹配 role_mapper.py 中的顺序
        mapping = {
            "技术": 1,  # config_expert → 执行技术
            "业务": 2,  # architect → 业务逻辑
            "意图": 3,  # intent_classifier → 意图理解
            "安全": 4,  # security_auditor → 安全合规
            "深度": 5,  # deep_tracker → 深度追踪
            "精度": 6,  # precision_tracker → 精度追踪
        }
        for name, expert_id in mapping.items():
            if f"@{name}" in text or f"@ {name}" in text:
                return expert_id
        return None
    

    def enter_single_mode(self, username: str, expert_id: int) -> str:
        """进入单列模式"""
        if not self.single_enabled:
            return "⚠️ 单列模式未启用，使用综合模式"
    
        session = self.get_session(username)
        session.mode = "single"
        session.active_expert = expert_id
        logger.info(f"✅ [enter_single_mode] session.mode={session.mode}, expert={expert_id}")
    
    # ✅ 统一映射（与 detect_expert_switch 一致）
        expert_names = {
            1: "执行技术",   # 技术
            2: "业务逻辑",   # 业务
            3: "意图理解",   # 意图
            4: "安全合规",   # 安全
            5: "深度追踪",   # 深度
            6: "精度锁定",   # 精度
        }
        logger.info(f"👤 {username} 进入单列模式，专家: {expert_names[expert_id]}")
        return f"✅ 已切换到【{expert_names[expert_id]}】专家单列模式。输入 /exit 退出单列模式。"
    
    def exit_single_mode(self, username: str) -> str:
        """退出单列模式，回到综合模式"""
        session = self.get_session(username)
        session.mode = "full"
        session.active_expert = None
        logger.info(f"👤 {username} 退出单列模式，回到综合模式")
        return "✅ 已退出单列模式，恢复综合专家会诊（1234轮答+总结）。"
    
    def get_mode(self, username: str) -> str:
        return self.get_session(username).mode
    
    def get_active_expert(self, username: str) -> Optional[int]:
        return self.get_session(username).active_expert
