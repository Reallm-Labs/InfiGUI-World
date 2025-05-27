import json
import os
from utils.logging import setup_logger

logger = setup_logger()

def load_config(config_path):
    """从文件加载配置"""
    if not os.path.exists(config_path):
        logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        return get_default_config()
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"从 {config_path} 加载配置成功")
        return config
    except Exception as e:
        logger.error(f"加载配置文件 {config_path} 失败: {e}")
        return get_default_config()

def get_default_config():
    """返回默认配置"""
    return {
        "server": {
            "host": "localhost",
            "port": 5000
        },
        "workers": {
            "max_workers": 4,
            "worker_types": ["env", "nginx", "reward"]
        },
        "environment": {
            "android": {
                "snapshot_dir": "/tmp/android_snapshots",
                "emulator_path": "emulator",
                "adb_path": "adb"
            }
        },
        "logging": {
            "level": "INFO",
            "log_dir": "logs"
        }
    }

def save_config(config, config_path):
    """保存配置到文件"""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"配置保存到 {config_path}")
        return True
    except Exception as e:
        logger.error(f"保存配置到 {config_path} 失败: {e}")
        return False
