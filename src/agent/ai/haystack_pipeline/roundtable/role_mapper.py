
import yaml
import os

class RoleMapper:
    """
    适配层：将 roles.yaml 中的角色映射到 config.yaml 中的专家配置
    不修改任何已有文件，只做读取和映射
    """
    
    def __init__(self):
        self.roles_config = self._load_roles_yaml()
        self.expert_config = self._load_config_yaml()
        self._build_mapping()
    
    def _load_roles_yaml(self):
        path = "/home/rick/knowpasser/src/agent/ai/roles.yaml"
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _load_config_yaml(self):
        path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _build_mapping(self):
        """建立映射关系：roles.yaml 中的角色 → config.yaml 中的专家配置"""
        config_map = {exp["role"]: exp for exp in self.expert_config["experts"]}
        
        # ✅ 更新适配映射表（6角色）
        adapt_map = {
            "config_expert": "tech",          # 执行技术
            "architect": "business",          # 业务逻辑
            "intent_classifier": "intent",    # 意图理解
            "security_auditor": "security",   # 安全合规
            "deep": "deep",                   # 深度追踪 
            "precision": "precision",         # 精度锁定 
        }
        
        self.mapping = {}
        
        for idx, role in enumerate(self.roles_config["roles"], start=1):
            roles_name = role["name"]
            config_role_name = adapt_map.get(roles_name, roles_name)
            config_obj = config_map.get(config_role_name)
            
            if config_obj:
                self.mapping[idx] = {
                    "role_id": idx,
                    "roles_name": roles_name,
                    "roles_weight": role["weight"],
                    "config_name": config_obj["name"],
                    "config_role": config_obj["role"],
                    "system_prompt": config_obj["system_prompt"],
                    "model": config_obj["model"],
                    "keywords": config_obj["keywords"],
                    "dimension": config_obj.get("dimension", 64),  # ✅ 新增维度
                }
            else:
                print(f"⚠️ 警告: roles.yaml 中的 '{roles_name}' 在 config.yaml 中无对应配置")
    
    def get_all_roles(self):
        return [self.mapping[key] for key in sorted(self.mapping.keys())]
    
    def get_role_by_id(self, role_id: int):
        return self.mapping.get(role_id)
    
    def get_weight_by_id(self, role_id: int):
        data = self.get_role_by_id(role_id)
        return data["roles_weight"] if data else None
    
    def get_prompt_by_id(self, role_id: int):
        data = self.get_role_by_id(role_id)
        return data["system_prompt"] if data else None
    
    def get_dimension_by_id(self, role_id: int):
        """获取指定角色的维度"""
        data = self.get_role_by_id(role_id)
        return data.get("dimension", 64) if data else 64
