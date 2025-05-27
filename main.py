import time
import uuid
import argparse
import signal
import sys
from api.coordinator import Coordinator
from environment.android_env import AndroidEnvironment
from worker.env_worker import EnvironmentWorker
from worker.nginx_worker import NginxWorker
from worker.reward_worker import RewardWorker
from api.api_server import ApiServer
from utils.logging import setup_logger
from utils.config import load_config, get_default_config

logger = setup_logger()

def parse_args():
    parser = argparse.ArgumentParser(description='Agentic Environment Framework')
    parser.add_argument('--mode', type=str, default='demo', help='运行模式: coordinator, worker, demo, api')
    parser.add_argument('--worker-type', type=str, default='env', help='Worker类型: env, nginx, reward')
    parser.add_argument('--env-type', type=str, default='android', help='环境类型: android, code_sandbox')
    parser.add_argument('--config', type=str, default='config.json', help='配置文件路径')
    parser.add_argument('--host', type=str, default='localhost', help='API服务器主机')
    parser.add_argument('--port', type=int, default=5000, help='API服务器端口')
    return parser.parse_args()

def handle_signal(signum, frame):
    """处理退出信号"""
    logger.info(f"收到信号 {signum}，正在退出...")
    sys.exit(0)

def main():
    # 注册信号处理
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    args = parse_args()
    
    try:
        config = load_config(args.config)
    except:
        logger.warning(f"无法加载配置文件，使用默认配置")
        config = get_default_config()
    
    if args.mode == 'coordinator':
        # 启动 Coordinator
        coordinator = Coordinator(config)
        coordinator.start()
    elif args.mode == 'worker':
        # 启动 Worker
        if args.worker_type == 'env':
            if args.env_type == 'android':
                # 使用配置中的 Android 环境参数（如果存在）
                android_config = config.get('environment', {}).get('android', {})
                env = AndroidEnvironment(android_config)
            worker = EnvironmentWorker(config, env)
        elif args.worker_type == 'nginx':
            worker = NginxWorker(config)
        elif args.worker_type == 'reward':
            worker = RewardWorker(config)
        else:
            logger.error(f"不支持的Worker类型: {args.worker_type}")
            return
        
        worker.start()
        
        # 保持进程运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            worker.stop()
    elif args.mode == 'api':
        # 创建协调器和API服务器
        coordinator = Coordinator(config)
        
        # 注册必要的 Worker
        if args.env_type == 'android':
            # 使用配置中的 Android 环境参数（如果存在）
            android_config = config.get('environment', {}).get('android', {})
            env = AndroidEnvironment(android_config)
        
        env_worker = EnvironmentWorker(config, env)
        reward_worker = RewardWorker(config)
        
        coordinator.register_worker(env_worker)
        coordinator.register_worker(reward_worker)
        
        # 启动 Worker
        coordinator.start_worker(env_worker.id)
        coordinator.start_worker(reward_worker.id)
        
        # 启动API服务器
        api_server = ApiServer(
            coordinator, 
            host=args.host,
            port=args.port
        )
        api_server.start()
        
        # 启动协调器监控
        coordinator.start()
        
    elif args.mode == 'demo':
        # 运行演示功能
        run_demo()
    else:
        logger.error(f"不支持的模式: {args.mode}")

def run_demo():
    print("\n===== 启动 Agentic Environment Framework 演示 =====\n")
    
    # 创建 Coordinator
    config = {"max_workers": 3, "port": 5000}
    coordinator = Coordinator(config)
    
    # 注册环境 Worker 和 Reward Worker
    android_env = AndroidEnvironment({"snapshot_dir": "/tmp/snapshots"})
    env_worker = EnvironmentWorker(config, android_env)
    reward_worker = RewardWorker(config)
    
    env_worker_id = coordinator.register_worker(env_worker)
    reward_worker_id = coordinator.register_worker(reward_worker)
    
    # 启动 Worker
    coordinator.start_worker(env_worker_id)
    coordinator.start_worker(reward_worker_id)
    
    print("\n1. 已创建和启动 Environment Worker 和 Reward Worker")
    print(f"   - Environment Worker ID: {env_worker_id}")
    print(f"   - Reward Worker ID: {reward_worker_id}")
    
    # 创建一个环境实例
    create_result = env_worker.handle_request({"action": "create"})
    
    if not create_result.get('success', False):
        print(f"\n创建环境失败: {create_result.get('error', '未知错误')}")
        return
    
    trajectory_id = create_result.get('trajectory_id')
    print(f"\n2. 已创建环境实例")
    print(f"   - Trajectory ID: {trajectory_id}")
    
    # 执行一些动作
    for i, action in enumerate([
        "click 100 200",
        "swipe 100 200 300 400",
        "text \"Hello World\"",
        "key back"
    ], 1):
        print(f"\n3.{i} 执行动作: {action}")
        step_result = env_worker.handle_request({
            "action": "step",
            "trajectory_id": trajectory_id,
            "command": action
        })
        
        if step_result.get('success', False):
            observation = step_result.get('observation', {})
            print(f"   结果: 成功")
            print(f"   观察到的信息: {observation}")
        else:
            print(f"   结果: 失败 - {step_result.get('error', '未知错误')}")
    
    # 保存环境状态
    save_result = env_worker.handle_request({
        "action": "save",
        "trajectory_id": trajectory_id
    })
    
    if save_result.get('success', False):
        print(f"\n4. 环境状态已保存")
    else:
        print(f"\n4. 保存环境状态失败: {save_result.get('error', '未知错误')}")
    
    # 计算奖励
    print("\n5. 计算轨迹的奖励值")
    reward_request = {
        "action": "calculate_reward",
        "reward_type": "rule_based",
        "trajectory_id": trajectory_id,
        "trajectory_data": {
            "actions": ["click 100 200", "swipe 100 200 300 400", "text \"Hello World\"", "key back"],
            "states": [
                {"screen": "HomeScreen", "interaction": None},
                {"screen": "HomeScreen", "interaction": "click", "target_element": "button1"},
                {"screen": "SecondScreen", "interaction": "swipe"},
                {"screen": "SecondScreen", "interaction": "text"},
                {"screen": "HomeScreen", "interaction": "key"}
            ],
            "success": True
        }
    }
    
    reward_result = reward_worker.handle_request(reward_request)
    
    if reward_result.get('success', False):
        print(f"   奖励值: {reward_result.get('reward', 0)}")
        print(f"   详细信息: {reward_result.get('details', {})}")
    else:
        print(f"   计算奖励失败: {reward_result.get('error', '未知错误')}")
    
    # 显示 Worker 状态
    for i in range(3):
        print(f"\n6.{i+1} 查看 Worker 状态")
        env_status = coordinator.check_worker_status(env_worker_id)
        reward_status = coordinator.check_worker_status(reward_worker_id)
        
        print(f"   Environment Worker: {env_status['status']}")
        print(f"   - 活跃轨迹数量: {env_status['resources'].get('active_trajectories', '未知')}")
        print(f"   - CPU使用率: {env_status['resources'].get('cpu_percent', '未知')}%")
        print(f"   - 内存使用率: {env_status['resources'].get('memory_percent', '未知')}%")
        
        print(f"   Reward Worker: {reward_status['status']}")
        print(f"   - 缓存大小: {reward_status['resources'].get('cache_size', '未知')}")
        print(f"   - CPU使用率: {reward_status['resources'].get('cpu_percent', '未知')}%")
        
        time.sleep(1)
    
    # 删除环境
    print("\n7. 删除环境")
    remove_result = env_worker.handle_request({
        "action": "remove",
        "trajectory_id": trajectory_id
    })
    
    if remove_result.get('success', False):
        print(f"   环境已删除")
    else:
        print(f"   删除环境失败: {remove_result.get('error', '未知错误')}")
    
    # 停止 Worker
    print("\n8. 停止 Worker")
    coordinator.stop_worker(env_worker_id)
    coordinator.stop_worker(reward_worker_id)
    print("   所有 Worker 已停止")
    
    print("\n===== 演示完成! =====\n")

if __name__ == "__main__":
    main()
