import uuid
from typing import Dict, Any, Optional
from utils.logging import setup_logger

logger = setup_logger()

class Environment:
    """
    环境基类，定义了所有环境需要实现的接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        logger.info(f"Initialized {self.__class__.__name__}")
    
    def create(self) -> Dict[str, Any]:
        """
        创建一个新的环境实例
        返回：包含 trajectory_id 和创建状态的字典
        """
        raise NotImplementedError("Subclasses must implement create()")
    
    def save(self, trajectory_id: str) -> Dict[str, Any]:
        """
        保存环境状态到对象存储中
        参数：trajectory_id - 轨迹ID
        返回：操作状态
        """
        raise NotImplementedError("Subclasses must implement save()")
    
    def load(self, trajectory_id: str) -> Dict[str, Any]:
        """
        从对象存储中加载环境状态
        参数：trajectory_id - 轨迹ID
        返回：操作状态
        """
        raise NotImplementedError("Subclasses must implement load()")
    
    def step(self, trajectory_id: str, action: str) -> Dict[str, Any]:
        """
        在环境中执行一个动作
        参数：
            trajectory_id - 轨迹ID
            action - 要执行的动作
        返回：执行结果，包括新的观察、奖励等
        """
        raise NotImplementedError("Subclasses must implement step()")
    
    def remove(self, trajectory_id: str) -> Dict[str, Any]:
        """
        从对象存储中删除环境状态
        参数：trajectory_id - 轨迹ID
        返回：操作状态
        """
        raise NotImplementedError("Subclasses must implement remove()")
