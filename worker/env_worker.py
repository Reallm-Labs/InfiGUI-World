import time
from typing import Dict, Any, Optional
from worker.base import Worker
from environment.base import Environment
from utils.logging import setup_logger

logger = setup_logger()

class EnvironmentWorker(Worker):
    """
    环境 Worker，负责管理环境的创建、步进、保存等操作
    """
    
    def __init__(self, config: Dict[str, Any], environment: Environment):
        super().__init__(config)
        self.environment = environment
        self.active_trajectories = {}  # trajectory_id -> last_active_time
        self.max_idle_time = config.get('max_idle_time', 3600)  # 默认1小时
    
    def _run(self):
        """Worker 主循环，定期清理不活跃的轨迹"""
        logger.info(f"Environment Worker {self.id} running")
        
        while self.running:
            self._cleanup_idle_trajectories()
            time.sleep(60)  # 每分钟检查一次
    
    def _cleanup_idle_trajectories(self):
        """清理长时间不活跃的轨迹"""
        current_time = time.time()
        for trajectory_id, last_active in list(self.active_trajectories.items()):
            if current_time - last_active > self.max_idle_time:
                logger.info(f"Cleaning up idle trajectory {trajectory_id}")
                try:
                    self.environment.remove(trajectory_id)
                    del self.active_trajectories[trajectory_id]
                except Exception as e:
                    logger.error(f"Error cleaning up trajectory {trajectory_id}: {e}")
    
    def _get_resources(self) -> Dict[str, Any]:
        """获取资源使用情况"""
        # 在实际应用中，应该获取真实的资源使用情况
        return {
            'active_trajectories': len(self.active_trajectories),
            'cpu_percent': 30.0,  # 示例值
            'memory_percent': 25.0,  # 示例值
            'active': self.running
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理环境请求"""
        action = request.get('action')
        trajectory_id = request.get('trajectory_id')
        
        if not action:
            return {'success': False, 'error': 'Missing action'}
        
        try:
            if action == 'create':
                # 创建新环境
                result = self.environment.create()
                if result['success']:
                    trajectory_id = result['trajectory_id']
                    self.active_trajectories[trajectory_id] = time.time()
                return result
                
            if not trajectory_id:
                return {'success': False, 'error': 'Missing trajectory_id'}
                
            # 更新最后活跃时间
            if trajectory_id in self.active_trajectories:
                self.active_trajectories[trajectory_id] = time.time()
                
            if action == 'save':
                # 保存环境
                return self.environment.save(trajectory_id)
                
            elif action == 'load':
                # 加载环境
                result = self.environment.load(trajectory_id)
                if result['success']:
                    self.active_trajectories[trajectory_id] = time.time()
                return result
                
            elif action == 'step':
                # 执行环境步骤
                command = request.get('command')
                if not command:
                    return {'success': False, 'error': 'Missing command for step action'}
                return self.environment.step(trajectory_id, command)
                
            elif action == 'remove':
                # 删除环境
                result = self.environment.remove(trajectory_id)
                if result['success'] and trajectory_id in self.active_trajectories:
                    del self.active_trajectories[trajectory_id]
                return result
                
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
                
        except Exception as e:
            logger.error(f"Error handling request {action} for trajectory {trajectory_id}: {e}")
            return {'success': False, 'error': str(e)}
