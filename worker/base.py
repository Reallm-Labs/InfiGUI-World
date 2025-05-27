import uuid
import time
import threading
from typing import Dict, Any, Optional
from utils.logging import setup_logger

logger = setup_logger()

class Worker:
    """
    Worker 基类，定义了所有 Worker 共有的接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.id = str(uuid.uuid4())
        self.running = False
        self.thread = None
        self.last_heartbeat = time.time()
        logger.info(f"Initialized {self.__class__.__name__} with ID {self.id}")
    
    def start(self):
        """启动 Worker"""
        if self.running:
            logger.warning(f"{self.__class__.__name__} {self.id} is already running")
            return
        
        logger.info(f"Starting {self.__class__.__name__} {self.id}")
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """停止 Worker"""
        if not self.running:
            logger.warning(f"{self.__class__.__name__} {self.id} is already stopped")
            return
        
        logger.info(f"Stopping {self.__class__.__name__} {self.id}")
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning(f"{self.__class__.__name__} {self.id} thread did not stop cleanly")
    
    def _run(self):
        """Worker 的主循环，由子类实现"""
        raise NotImplementedError("Subclasses must implement _run()")
    
    def update_config(self, config: Dict[str, Any]):
        """更新 Worker 配置"""
        logger.info(f"Updating config for {self.__class__.__name__} {self.id}")
        self.config.update(config)
    
    def heartbeat(self) -> Dict[str, Any]:
        """返回 Worker 的状态信息"""
        self.last_heartbeat = time.time()
        return {
            'status': 'running' if self.running else 'stopped',
            'resources': self._get_resources(),
            'last_heartbeat': self.last_heartbeat
        }
    
    def _get_resources(self) -> Dict[str, Any]:
        """获取 Worker 资源使用情况"""
        # 这个方法应该由子类实现，返回 CPU、内存等资源使用情况
        # 这里提供一个简单的默认实现
        return {
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'active': self.running
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求，由子类实现"""
        raise NotImplementedError("Subclasses must implement handle_request()")
