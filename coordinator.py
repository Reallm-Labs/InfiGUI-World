import time
import uuid
import threading
from typing import Dict, List, Any, Optional
from utils.logging import setup_logger

logger = setup_logger()

class Coordinator:
    """
    协调器类，负责管理 Worker、监控状态、资源分配等
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.workers = {}  # worker_id -> worker
        self.worker_status = {}  # worker_id -> status
        self.worker_lock = threading.Lock()
        self.running = False
        self.monitor_thread = None
        self.id = str(uuid.uuid4())
        logger.info(f"Coordinator initialized with ID {self.id}")
    
    def start(self):
        """启动协调器"""
        logger.info("Starting coordinator...")
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_workers)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        # 在实际应用中，这里可能会启动一个 HTTP 服务器或其他 RPC 接口
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """停止协调器"""
        logger.info("Stopping coordinator...")
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        # 停止所有 worker
        for worker_id, worker in list(self.workers.items()):
            self.stop_worker(worker_id)
    
    def register_worker(self, worker) -> str:
        """注册一个新的 Worker"""
        worker_id = worker.id if hasattr(worker, 'id') else str(uuid.uuid4())
        
        with self.worker_lock:
            self.workers[worker_id] = worker
            self.worker_status[worker_id] = {
                'status': 'idle',
                'last_heartbeat': time.time(),
                'resources': {},
                'type': worker.__class__.__name__
            }
        
        logger.info(f"Registered worker {worker_id} of type {worker.__class__.__name__}")
        return worker_id
    
    def unregister_worker(self, worker_id: str) -> bool:
        """注销一个 Worker"""
        with self.worker_lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
                del self.worker_status[worker_id]
                logger.info(f"Unregistered worker {worker_id}")
                return True
            else:
                logger.warning(f"Attempted to unregister non-existent worker {worker_id}")
                return False
    
    def start_worker(self, worker_id: str) -> bool:
        """启动一个 Worker"""
        with self.worker_lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                if hasattr(worker, 'start') and callable(worker.start):
                    worker.start()
                    self.worker_status[worker_id]['status'] = 'running'
                    logger.info(f"Started worker {worker_id}")
                    return True
            
            logger.warning(f"Failed to start worker {worker_id}")
            return False
    
    def stop_worker(self, worker_id: str) -> bool:
        """停止一个 Worker"""
        with self.worker_lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                if hasattr(worker, 'stop') and callable(worker.stop):
                    worker.stop()
                    self.worker_status[worker_id]['status'] = 'stopped'
                    logger.info(f"Stopped worker {worker_id}")
                    return True
            
            logger.warning(f"Failed to stop worker {worker_id}")
            return False
    
    def restart_worker(self, worker_id: str) -> bool:
        """重启一个 Worker"""
        if self.stop_worker(worker_id):
            return self.start_worker(worker_id)
        return False
    
    def update_worker_config(self, worker_id: str, config: Dict[str, Any]) -> bool:
        """热更新 Worker 配置"""
        with self.worker_lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                if hasattr(worker, 'update_config') and callable(worker.update_config):
                    worker.update_config(config)
                    logger.info(f"Updated config for worker {worker_id}")
                    return True
            
            logger.warning(f"Failed to update config for worker {worker_id}")
            return False
    
    def check_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """检查 Worker 状态"""
        with self.worker_lock:
            if worker_id in self.worker_status:
                return self.worker_status[worker_id]
            return None
    
    def _monitor_workers(self):
        """监控所有 Worker 的状态"""
        logger.info("Starting worker monitor thread")
        
        while self.running:
            current_time = time.time()
            
            with self.worker_lock:
                for worker_id, worker in list(self.workers.items()):
                    # 检查心跳
                    if hasattr(worker, 'heartbeat') and callable(worker.heartbeat):
                        try:
                            status = worker.heartbeat()
                            self.worker_status[worker_id].update({
                                'last_heartbeat': current_time,
                                'resources': status.get('resources', {}),
                                'status': status.get('status', 'unknown')
                            })
                        except Exception as e:
                            logger.error(f"Error getting heartbeat from worker {worker_id}: {e}")
                            self.worker_status[worker_id]['status'] = 'error'
                    
                    # 检查是否需要重启
                    if (self.worker_status[worker_id]['status'] == 'error' or 
                        current_time - self.worker_status[worker_id]['last_heartbeat'] > 60):  # 60秒无响应
                        logger.warning(f"Worker {worker_id} seems dead, attempting restart")
                        self.restart_worker(worker_id)
            
            time.sleep(10)  # 每10秒检查一次
        
        logger.info("Worker monitor thread stopped")
    
    def allocate_resources(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """根据需求分配资源"""
        # 在实际应用中，这里会实现复杂的资源分配算法
        # 这里只是一个简单的示例
        result = {
            'success': True,
            'allocated_resources': {},
            'worker_id': None
        }
        
        with self.worker_lock:
            for worker_id, status in self.worker_status.items():
                if status['status'] == 'idle' or status['status'] == 'running':
                    # 简单示例，实际中需要检查具体资源是否满足要求
                    result['worker_id'] = worker_id
                    result['allocated_resources'] = {'cpu': 1, 'memory': '1G'}
                    break
            else:
                result['success'] = False
        
        return result
