import logging
import os
import sys
from datetime import datetime

def setup_logger(name=None, level=logging.INFO):
    """配置并返回一个logger"""
    if name is None:
        name = __name__
    
    logger = logging.getLogger(name)
    
    # 如果logger已经有handler，不重复添加
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 创建控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 创建文件handler
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f'{datetime.now().strftime("%Y%m%d")}.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    
    # 创建formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # 添加handlers到logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger
