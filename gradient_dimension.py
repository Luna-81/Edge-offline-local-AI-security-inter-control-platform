"""
维度梯度加减法系统
支持6议会成员维度的动态调整
"""

from enum import Enum
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime  # ✅ 修复：导入 datetime

logger = logging.getLogger("GradientDimension")

class GradientStep(Enum):
    """梯度步长"""
    MICRO = 8      # 微调：±8维
    SMALL = 16     # 小幅：±16维
    MEDIUM = 32    # 中幅：±32维
    LARGE = 64     # 大幅：±64维
    XLARGE = 128   # 超大幅：±128维

class DimensionGradient:
    """
    维度梯度控制器
    支持每个议员独立的维度加减
    """
    
    def __init__(self):
        # 6位议员的当前维度（初始值）
        self.current_dimensions = {
            1: 128,  # 意图理解
            2: 64,   # 安全合规
            3: 64,   # 业务逻辑
            4: 32,   # 执行技术
            5: 16,   # 深度追踪
            6: 16,   # 精度锁定
        }
        
        # 维度范围（最小/最大）
        self.dimension_ranges = {
            1: (32, 512),   # 意图理解：32-512
            2: (32, 256),   # 安全合规：32-256
            3: (32, 256),   # 业务逻辑：32-256
            4: (16, 512),   # 执行技术：16-512
            5: (8, 256),    # 深度追踪：8-256
            6: (8, 256),    # 精度锁定：8-256
        }
        
        # 专家名称映射
        self.expert_names = {
            1: "🧠意图理解", 2: "🔒安全合规", 3: "📊业务逻辑",
            4: "⚙️执行技术", 5: "🔍深度追踪", 6: "🎯精度锁定"
        }
        
        # 梯度历史（用于回滚和追踪）
        self.history: List[Dict] = []
        
        # 初始快照（用于重置）
        self._snapshot = self.current_dimensions.copy()
    
    def add_dimension(self, role_id: int, steps: int = 1, step_size: GradientStep = GradientStep.MEDIUM) -> bool:
        """
        给指定议员增加维度
        steps: 步数
        step_size: 步长
        """
        if role_id not in self.current_dimensions:
            return False
        
        current = self.current_dimensions[role_id]
        increment = steps * step_size.value
        new_dim = min(current + increment, self.dimension_ranges[role_id][1])
        
        if new_dim == current:
            logger.info(f"⚠️ 议员{role_id} 已达上限 {self.dimension_ranges[role_id][1]}维")
            return False
        
        # 记录历史
        self.history.append({
            "role_id": role_id,
            "name": self.expert_names.get(role_id, f"专家{role_id}"),
            "operation": "add",
            "from": current,
            "to": new_dim,
            "steps": steps,
            "step_size": step_size.value,
            "timestamp": datetime.now().isoformat()  # ✅ 现在可以使用了
        })
        
        self.current_dimensions[role_id] = new_dim
        logger.info(f"📈 {self.expert_names.get(role_id, f'专家{role_id}')}: {current} → {new_dim} (+{new_dim-current})维")
        return True
    
    def subtract_dimension(self, role_id: int, steps: int = 1, step_size: GradientStep = GradientStep.MEDIUM) -> bool:
        """
        给指定议员减少维度
        """
        if role_id not in self.current_dimensions:
            return False
        
        current = self.current_dimensions[role_id]
        decrement = steps * step_size.value
        new_dim = max(current - decrement, self.dimension_ranges[role_id][0])
        
        if new_dim == current:
            logger.info(f"⚠️ 议员{role_id} 已达下限 {self.dimension_ranges[role_id][0]}维")
            return False
        
        self.history.append({
            "role_id": role_id,
            "name": self.expert_names.get(role_id, f"专家{role_id}"),
            "operation": "subtract",
            "from": current,
            "to": new_dim,
            "steps": steps,
            "step_size": step_size.value,
            "timestamp": datetime.now().isoformat()  # ✅ 现在可以使用了
        })
        
        self.current_dimensions[role_id] = new_dim
        logger.info(f"📉 {self.expert_names.get(role_id, f'专家{role_id}')}: {current} → {new_dim} (-{current-new_dim})维")
        return True
    
    def adjust_all(self, role_ids: List[int], direction: str, steps: int = 1, step_size: GradientStep = GradientStep.MEDIUM) -> Dict:
        """
        批量调整多个议员
        direction: "up" 或 "down"
        """
        results = {}
        for role_id in role_ids:
            if direction == "up":
                results[role_id] = self.add_dimension(role_id, steps, step_size)
            else:
                results[role_id] = self.subtract_dimension(role_id, steps, step_size)
        return results
    
    def get_dimension(self, role_id: int) -> int:
        """获取指定议员的当前维度"""
        return self.current_dimensions.get(role_id, 0)
    # gradient_dimension.py
# 在 get_dimension() 方法后面添加

    def set_dimension(self, role_id: int, new_dim: int) -> bool:
        """
        直接设置指定专家的维度（用于动态调整和预设）
        """
        if role_id not in self.current_dimensions:
            return False
        
        min_dim, max_dim = self.dimension_ranges[role_id]
        clamped = max(min_dim, min(new_dim, max_dim))
        
        old = self.current_dimensions[role_id]
        if old == clamped:
            return False
        
        self.history.append({
            "role_id": role_id,
            "name": self.expert_names.get(role_id, f"专家{role_id}"),
            "operation": "set",
            "from": old,
            "to": clamped,
            "steps": 0,
            "step_size": 0,
            "timestamp": datetime.now().isoformat()
        })
        
        self.current_dimensions[role_id] = clamped
        logger.info(f"🎯 {self.expert_names.get(role_id, f'专家{role_id}')}: {old} → {clamped} 维")
        return True
    
    def get_all_dimensions(self) -> Dict:
        """获取所有议员的当前维度"""
        return self.current_dimensions.copy()
    
    def reset(self):
        """重置到初始维度"""
        self.current_dimensions = self._snapshot.copy()
        self.history.clear()
        logger.info("🔄 维度已重置到初始状态")
    
    def print_status(self):
        """打印当前维度状态"""
        print("\n" + "="*60)
        print("📊 6议会维度状态")
        print("="*60)
        for role_id, dim in self.current_dimensions.items():
            name = self.expert_names.get(role_id, f"专家{role_id}")
            range_min, range_max = self.dimension_ranges[role_id]
            bar = "█" * (dim // 16) + "░" * ((range_max - dim) // 16)
            print(f"  {name}: {dim}维 [{range_min}-{range_max}] {bar}")
        print("="*60 + "\n")
    
    def get_history(self) -> List[Dict]:
        """获取调整历史"""
        return self.history


class AutoGradientController:
    """自动梯度调节器"""
    
    def __init__(self, gradient: DimensionGradient):
        self.gradient = gradient
        
        # 触发词配置
        self.trigger_config = {
            "tech": {
                "keywords": ["代码", "实现", "部署", "算法", "架构", "性能", "优化", "开发"],
                "target_roles": [4, 6],
                "boost_steps": 2
            },
            "business": {
                "keywords": ["业务", "流程", "审批", "制度", "规范", "场景", "应用"],
                "target_roles": [3, 1],
                "boost_steps": 2
            },
            "security": {
                "keywords": ["安全", "风险", "违规", "合规", "敏感", "隐私", "越狱"],
                "target_roles": [2],
                "boost_steps": 2
            },
            "deep": {
                "keywords": ["时序", "因果", "追溯", "根因", "历史", "演变", "链路"],
                "target_roles": [5],
                "boost_steps": 2
            },
            "ux": {
                "keywords": ["用户体验", "新手", "易懂", "友好", "引导", "操作步骤", "易用"],
                "target_roles": [1, 3],
                "boost_steps": 1
            },
            # ✅ 新增：性能问题检测
            "performance": {
                "keywords": ["慢", "卡顿", "延迟", "响应慢", "超时", "瓶颈", "耗时长"],
                "target_roles": [4, 5, 6],  # 执行技术 + 深度追踪 + 精度锁定
                "boost_steps": 3  # 性能问题需要更深入分析，步数更多
            }
        }
    
    def analyze_complexity(self, user_input: str) -> Tuple[str, int]:
        """
        分析问题复杂度
        返回：(级别, 推荐维度)
        """
        # 计算基础复杂度
        word_count = len(user_input)
        tech_keywords = sum(1 for kw in self.trigger_config["tech"]["keywords"] if kw in user_input)
        biz_keywords = sum(1 for kw in self.trigger_config["business"]["keywords"] if kw in user_input)
        
        # 加权分数
        score = word_count * 0.05 + tech_keywords * 8 + biz_keywords * 5
        
        if score < 20:
            return "simple", 32
        elif score < 40:
            return "medium", 64
        elif score < 60:
            return "complex", 128
        elif score < 80:
            return "expert", 256
        else:
            return "master", 512
    
    def auto_adjust(self, user_input: str) -> Dict:
        """
        自动调整所有议员维度
        返回调整结果
        """
        level, recommended_dim = self.analyze_complexity(user_input)
        
        print(f"\n📊 问题复杂度: {level} (推荐基础维度: {recommended_dim})")
        
        adjustments = {}
        
        # 检查每个触发条件
        for trigger_name, config in self.trigger_config.items():
            # 检查关键词是否匹配
            if any(kw in user_input for kw in config["keywords"]):
                print(f"  🔍 检测到 {trigger_name} 特征，升维相关专家")
                
                for role_id in config["target_roles"]:
                    # 计算目标维度（不超过上限）
                    current = self.gradient.get_dimension(role_id)
                    max_dim = self.gradient.dimension_ranges[role_id][1]
                    target = min(recommended_dim, max_dim)
                    
                    # 计算需要的步数
                    if target > current:
                        steps = max(1, (target - current) // 16)
                        self.gradient.add_dimension(role_id, steps)
                        adjustments[role_id] = f"升维到 {self.gradient.get_dimension(role_id)}维"
        
        # 如果没有触发任何升维，保持基础维度
        if not adjustments:
            # 所有专家设置为基础维度
            for role_id in self.gradient.current_dimensions.keys():
                current = self.gradient.get_dimension(role_id)
                max_dim = self.gradient.dimension_ranges[role_id][1]
                target = min(recommended_dim, max_dim)
                
                if target > current:
                    steps = max(1, (target - current) // 16)
                    self.gradient.add_dimension(role_id, steps)
                    adjustments[role_id] = f"升维到 {self.gradient.get_dimension(role_id)}维"
        
        return adjustments
    
    def preset_adjust(self, preset: str):
        """
        预设调整方案
        presets: "quick", "standard", "deep", "expert"
        """
        presets_config = {
            "quick": {
                "description": "快速回答（低维度）",
                "target_dim": 32,
                "step_size": GradientStep.LARGE
            },
            "standard": {
                "description": "标准分析（中等维度）",
                "target_dim": 64,
                "step_size": GradientStep.MEDIUM
            },
            "deep": {
                "description": "深度分析（高维度）",
                "target_dim": 128,
                "step_size": GradientStep.MEDIUM
            },
            "expert": {
                "description": "专家级分析（最高维度）",
                "target_dim": 256,
                "step_size": GradientStep.SMALL
            }
        }
        
        if preset not in presets_config:
            print(f"❌ 未知预设: {preset}")
            return
        
        config = presets_config[preset]
        target_dim = config["target_dim"]
        step_size = config["step_size"]
        
        print(f"\n🎯 应用预设: {config['description']}")
        
        for role_id in self.gradient.current_dimensions.keys():
            current = self.gradient.get_dimension(role_id)
            max_dim = self.gradient.dimension_ranges[role_id][1]
            target = min(target_dim, max_dim)
            
            if target > current:
                steps = max(1, (target - current) // step_size.value)
                self.gradient.add_dimension(role_id, steps, step_size)
            elif target < current:
                steps = max(1, (current - target) // step_size.value)
                self.gradient.subtract_dimension(role_id, steps, step_size)
