import time
import json
import os
import subprocess
from typing import Dict, Any, List, Optional
from worker.base import Worker
from utils.logging import setup_logger

logger = setup_logger()

class RewardWorker(Worker):
    """
    Reward Worker，负责计算奖励值
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # ---- ADB 相关配置 ----
        self.adb_path: str = config.get("adb_path", "/root/Android/Sdk/platform-tools/adb")
        # AndroidEnvironment 默认快照目录 – 用于根据 trajectory_id 找到 device_id
        self.snapshot_dir: str = config.get("snapshot_dir", "/tmp/android_snapshots")

        # 兼容旧的 reward 逻辑（保留）
        self.reward_functions = self._load_reward_functions(config)
        self.cache: Dict[str, Any] = {}

    def _load_reward_functions(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """加载奖励函数"""
        # 在实际应用中，可能会从配置文件或者模型中加载奖励函数
        # 这里返回一些示例函数
        return {
            'task_completion': self._reward_task_completion,
            'efficiency': self._reward_efficiency,
            'rule_based': self._rule_based_reward
        }
    
    def _run(self):
        """Worker 主循环，可用于清理缓存等工作"""
        logger.info(f"Reward Worker {self.id} running")
        
        while self.running:
            # 清理较老的缓存条目
            current_time = time.time()
            for key in list(self.cache.keys()):
                if current_time - self.cache[key]['timestamp'] > 3600:  # 1小时过期
                    del self.cache[key]
            
            time.sleep(300)  # 每5分钟清理一次
    
    def _get_resources(self) -> Dict[str, Any]:
        """获取资源使用情况"""
        return {
            'cache_size': len(self.cache),
            'cpu_percent': 15.0,  # 示例值
            'memory_percent': 10.0,  # 示例值
            'active': self.running
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理奖励计算请求"""
        action = request.get('action')
        
        if not action:
            return {'success': False, 'error': 'Missing action'}
        
        try:

            # ------------------------------------------------------------------
            # 1) 新增 – ADB 执行逻辑
            # ------------------------------------------------------------------
            if action in ("execute_adb",) or (action == "calculate_reward" and request.get("adb_command")):
                trajectory_id = request.get("trajectory_id")
                adb_command = request.get("adb_command")

                if not trajectory_id or not adb_command:
                    return {"success": False, "error": "Missing trajectory_id or adb_command"}

                device_id = request.get("device_id") or self._resolve_device_id(trajectory_id)
                if not device_id:
                    return {"success": False, "error": "Cannot resolve device_id for given trajectory_id"}

                return self._execute_adb_helper(device_id, adb_command)

            # ------------------------------------------------------------------
            # 2) 兼容旧的奖励计算逻辑（如仍需要）
            # ------------------------------------------------------------------
            if action == 'calculate_reward':
                reward_type = request.get('reward_type', 'rule_based')
                trajectory_id = request.get('trajectory_id')
                trajectory_data = request.get('trajectory_data')
                
                if not trajectory_id or not trajectory_data:
                    return {'success': False, 'error': 'Missing trajectory_id or trajectory_data'}
                
                # 检查缓存
                cache_key = f"{trajectory_id}:{reward_type}"
                if cache_key in self.cache:
                    logger.info(f"Cache hit for reward calculation {cache_key}")
                    return self.cache[cache_key]['result']
                
                # 计算奖励
                if reward_type in self.reward_functions:
                    reward_func = self.reward_functions[reward_type]
                    result = reward_func(trajectory_data)
                    
                    # 缓存结果
                    self.cache[cache_key] = {
                        'result': result,
                        'timestamp': time.time()
                    }
                    
                    return result
                else:
                    return {'success': False, 'error': f'Unknown reward type: {reward_type}'}
                
            elif action == 'clear_cache':
                # 清除缓存
                trajectory_id = request.get('trajectory_id')
                
                if trajectory_id:
                    # 清除特定轨迹的缓存
                    keys_to_remove = [key for key in self.cache if key.startswith(f"{trajectory_id}:")]
                    for key in keys_to_remove:
                        del self.cache[key]
                    return {'success': True, 'cleared_entries': len(keys_to_remove)}
                else:
                    # 清除所有缓存
                    cache_size = len(self.cache)
                    self.cache.clear()
                    return {'success': True, 'cleared_entries': cache_size}
                
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
                
        except Exception as e:
            logger.error(f"Error handling reward request {action}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _reward_task_completion(self, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于任务完成情况的奖励函数
        """
        try:
            # 在实际应用中，这里应该实现复杂的奖励计算逻辑
            goal = trajectory_data.get('goal', {})
            final_state = trajectory_data.get('final_state', {})
            
            # 简化的示例：检查目标是否达成
            success = False
            for key, value in goal.items():
                if key in final_state and final_state[key] == value:
                    success = True
                else:
                    success = False
                    break
            
            reward = 1.0 if success else 0.0
            
            return {
                'success': True,
                'reward': reward,
                'details': {
                    'task_completed': success
                }
            }
        except Exception as e:
            logger.error(f"Error in reward_task_completion: {e}")
            return {'success': False, 'error': str(e)}
    
    def _reward_efficiency(self, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于效率的奖励函数
        """
        try:
            actions = trajectory_data.get('actions', [])
            goal_reached = trajectory_data.get('goal_reached', False)
            
            if not goal_reached:
                reward = -0.1  # 未达成目标给予小的负奖励
            else:
                # 步骤越少奖励越高
                num_actions = len(actions)
                if num_actions == 0:
                    reward = 0
                else:
                    reward = 1.0 / num_actions  # 简单的反比例关系
            
            return {
                'success': True,
                'reward': reward,
                'details': {
                    'num_actions': len(actions),
                    'goal_reached': goal_reached
                }
            }
        except Exception as e:
            logger.error(f"Error in reward_efficiency: {e}")
            return {'success': False, 'error': str(e)}
    
    def _rule_based_reward(self, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于规则的奖励函数
        """
        try:
            actions = trajectory_data.get('actions', [])
            states = trajectory_data.get('states', [])
            
            reward = 0.0
            details = {}
            
            # 在实际应用中，这里会实现基于特定规则的复杂奖励计算
            # 这里只是一个简单示例
            
            # 示例规则1：操作数量惩罚
            action_penalty = -0.01 * len(actions)
            reward += action_penalty
            details['action_penalty'] = action_penalty
            
            # 示例规则2：特定状态奖励
            target_achieved = False
            for state in states:
                if 'target_element' in state and state.get('interaction') == 'click':
                    reward += 0.5
                    target_achieved = True
                    details['target_achieved'] = True
                    break
            
            if not target_achieved:
                details['target_achieved'] = False
            
            # 示例规则3：最终成功奖励
            if trajectory_data.get('success', False):
                reward += 1.0
                details['success_reward'] = 1.0
            
            return {
                'success': True,
                'reward': reward,
                'details': details
            }
        except Exception as e:
            logger.error(f"Error in rule_based_reward: {e}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_device_id(self, trajectory_id: str) -> Optional[str]:
        """尝试通过快照元数据解析出 emulator device_id。"""
        meta_path = os.path.join(self.snapshot_dir, f"{trajectory_id}.json")
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
            return meta.get("device_id")
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Failed to parse snapshot meta {meta_path}: {exc}")
            return None

    def _execute_adb_helper(self, device_id: str, adb_command: List[str] | str) -> Dict[str, Any]:
        """实际执行 adb 并返回结果。"""
        cmd_list: List[str]
        if isinstance(adb_command, str):
            cmd_list = adb_command.split()
        else:
            cmd_list = adb_command

        full_cmd = [self.adb_path, "-s", device_id] + cmd_list
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, check=False)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "executed_cmd": " ".join(full_cmd),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
