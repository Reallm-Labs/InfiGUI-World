import json
import logging
import threading
from flask import Flask, request, jsonify
from environment.android_env import AndroidEnvironment
from utils.logging import setup_logger
from .coordinator import Coordinator

logger = setup_logger()

class ApiServer:
    """HTTP API 服务器，提供与 Coordinator 和 Worker 交互的接口"""
    
    def __init__(self, coordinator, host='localhost', port=5000):
        self.app = Flask(__name__)
        self.coordinator = coordinator
        self.host = host
        self.port = port
        self.setup_routes()
        logger.info(f"API Server 初始化在 {host}:{port}")
    
    def setup_routes(self):
        """设置 API 路由"""
        # 协调器相关接口
        self.app.route('/api/coordinator/status')(self.get_coordinator_status)
        self.app.route('/api/coordinator/workers')(self.list_workers)
        
        # Worker 相关接口
        self.app.route('/api/workers/<worker_id>/start', methods=['POST'])(self.start_worker)
        self.app.route('/api/workers/<worker_id>/stop', methods=['POST'])(self.stop_worker)
        self.app.route('/api/workers/<worker_id>/restart', methods=['POST'])(self.restart_worker)
        self.app.route('/api/workers/<worker_id>/config', methods=['PUT'])(self.update_worker_config)
        self.app.route('/api/workers/<worker_id>/status')(self.get_worker_status)
        
        # 环境相关接口
        self.app.route('/api/env/create', methods=['POST'])(self.create_env)
        self.app.route('/api/env/save', methods=['POST'])(self.save_env)
        self.app.route('/api/env/load', methods=['POST'])(self.load_env)
        self.app.route('/api/env/step', methods=['POST'])(self.step_env)
        self.app.route('/api/env/remove', methods=['POST'])(self.remove_env)

        # 列出支持的动作类型（便于前端构建动态表单）
        self.app.route('/api/env/actions')(self.list_env_actions)

        # Reward related interface
        self.app.route('/api/reward/calculate', methods=['POST'])(self.calculate_reward)

    def start(self):
        """启动 API 服务器"""
        threading.Thread(
            target=self.app.run,
            kwargs={
                'host': self.host,
                'port': self.port,
                'debug': False,
                'use_reloader': False
            }
        ).start()
        logger.info(f"API Server 开始运行在 {self.host}:{self.port}")

    # Coordinator 接口实现
    def get_coordinator_status(self):
        return jsonify({
            'status': 'running' if self.coordinator.running else 'stopped',
            'id': self.coordinator.id,
            'worker_count': len(self.coordinator.workers)
        })
    
    def list_workers(self):
        return jsonify({
            'workers': [
                {
                    'id': worker_id,
                    'type': status['type'],
                    'status': status['status'],
                    'last_heartbeat': status['last_heartbeat']
                }
                for worker_id, status in self.coordinator.worker_status.items()
            ]
        })
    
    # Worker 接口实现
    def start_worker(self, worker_id):
        success = self.coordinator.start_worker(worker_id)
        return jsonify({'success': success})
    
    def stop_worker(self, worker_id):
        success = self.coordinator.stop_worker(worker_id)
        return jsonify({'success': success})
    
    def restart_worker(self, worker_id):
        success = self.coordinator.restart_worker(worker_id)
        return jsonify({'success': success})
    
    def update_worker_config(self, worker_id):
        config = request.json
        success = self.coordinator.update_worker_config(worker_id, config)
        return jsonify({'success': success})
    
    def get_worker_status(self, worker_id):
        status = self.coordinator.check_worker_status(worker_id)
        if status:
            return jsonify(status)
        return jsonify({'error': 'Worker not found'}), 404
    
    # 环境接口实现
    def create_env(self):
        # 找到环境 worker
        env_worker = None
        for worker_id, worker in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'EnvironmentWorker':
                env_worker = worker
                break
        
        if not env_worker:
            return jsonify({'success': False, 'error': '未找到环境 Worker'}), 404
        
        result = env_worker.handle_request({'action': 'create'})
        return jsonify(result)
    
    def save_env(self):
        data = request.json
        trajectory_id = data.get('trajectory_id')
        
        if not trajectory_id:
            return jsonify({'success': False, 'error': '缺少 trajectory_id'}), 400
        
        env_worker = None
        for worker_id, worker in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'EnvironmentWorker':
                env_worker = worker
                break
        
        if not env_worker:
            return jsonify({'success': False, 'error': '未找到环境 Worker'}), 404
        
        result = env_worker.handle_request({
            'action': 'save',
            'trajectory_id': trajectory_id
        })
        return jsonify(result)
    
    def load_env(self):
        data = request.json
        trajectory_id = data.get('trajectory_id')
        
        if not trajectory_id:
            return jsonify({'success': False, 'error': '缺少 trajectory_id'}), 400
        
        env_worker = None
        for worker_id, worker in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'EnvironmentWorker':
                env_worker = worker
                break
        
        if not env_worker:
            return jsonify({'success': False, 'error': '未找到环境 Worker'}), 404
        
        result = env_worker.handle_request({
            'action': 'load',
            'trajectory_id': trajectory_id
        })
        return jsonify(result)
    
    def step_env(self):
        data = request.json or {}
        trajectory_id = data.get('trajectory_id')

        # 支持多种动作表示：
        # 1) legacy "command" 字符串，如 "click 100 200"
        # 2) "command" dict / JSON，直接映射 android_world.env.json_action.JSONAction
        # 3) 新增 "action" 字段，效果同 "command"，便于前端语义化调用
        command = data.get('command') if 'command' in data else None
        if command is None:
            command = data.get('action')  # allow alias
        print('Cur action is:', command)

        # null/empty guard
        if trajectory_id is None or command is None:
            return jsonify({'success': False, 'error': '缺少 trajectory_id 或 action/command'}), 400
        
        env_worker = None
        for worker_id, worker in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'EnvironmentWorker':
                env_worker = worker
                break
        
        if not env_worker:
            return jsonify({'success': False, 'error': '未找到环境 Worker'}), 404
        
        # 直接把 command 原样传递，底层 Environment 会自行解析（DSL 或 JSONAction）。
        result = env_worker.handle_request({
            'action': 'step',
            'trajectory_id': trajectory_id,
            'command': command
        })
        return jsonify(result)
    
    def remove_env(self):
        data = request.json
        trajectory_id = data.get('trajectory_id')
        
        if not trajectory_id:
            return jsonify({'success': False, 'error': '缺少 trajectory_id'}), 400
        
        env_worker = None
        for worker_id, worker in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'EnvironmentWorker':
                env_worker = worker
                break
        
        if not env_worker:
            return jsonify({'success': False, 'error': '未找到环境 Worker'}), 404
        
        result = env_worker.handle_request({
            'action': 'remove',
            'trajectory_id': trajectory_id
        })
        return jsonify(result)

    # Reward interface implementation
    def calculate_reward(self):
        data = request.json
        reward_type = data.get('reward_type')
        trajectory_id = data.get('trajectory_id')
        trajectory_data = data.get('trajectory_data')

        if not reward_type or not trajectory_id or not trajectory_data:
            return jsonify({'success': False, 'error': 'Missing reward_type, trajectory_id, or trajectory_data'}), 400

        # Find reward worker
        reward_worker = None
        for worker_id, worker_obj in self.coordinator.workers.items():
            if self.coordinator.worker_status[worker_id]['type'] == 'RewardWorker':
                reward_worker = worker_obj
                break
        
        if not reward_worker:
            return jsonify({'success': False, 'error': 'RewardWorker not found'}), 404

        result = reward_worker.handle_request({
            'action': 'calculate_reward',
            'reward_type': reward_type,
            'trajectory_id': trajectory_id,
            'trajectory_data': trajectory_data
        })
        return jsonify(result)

    def list_env_actions(self):
        """返回后端当前支持的 JSONAction 类型列表。"""
        try:
            from android_world.env import json_action as ja  # type: ignore
            actions = list(getattr(ja, '_ACTION_TYPES', []))
            return jsonify({'success': True, 'actions': actions})
        except Exception as exc:  # pragma: no cover
            logger.warning(f'Failed to fetch action list: {exc}')
            return jsonify({'success': False, 'error': str(exc)}), 500
