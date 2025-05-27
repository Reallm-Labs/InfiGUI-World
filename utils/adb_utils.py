import subprocess
import re
import time
import os
from typing import List, Dict, Any, Optional, Tuple
from utils.logging import setup_logger

logger = setup_logger()

class ADBUtils:
    """ADB 工具类，提供与 Android 设备交互的实用工具"""
    
    def __init__(self, adb_path: str = 'adb'):
        self.adb_path = adb_path
        self._ensure_adb_server()
    
    def _ensure_adb_server(self):
        """确保 ADB 服务器正在运行"""
        try:
            subprocess.run([self.adb_path, "start-server"], check=True, capture_output=True)
            logger.info("ADB 服务器已启动")
        except subprocess.CalledProcessError as e:
            logger.error(f"启动 ADB 服务器失败: {e}")
            raise RuntimeError(f"无法启动 ADB 服务器: {e}")
    
    def execute(self, device_id: Optional[str] = None, *args, check: bool = True, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        """
        执行 ADB 命令
        
        参数:
            device_id: 设备 ID，如 "emulator-5554"，如果为 None，则不指定设备
            args: 要传递给 ADB 的命令和参数
            check: 如果为 True，非零返回代码将引发 CalledProcessError
            timeout: 命令执行超时（秒）
            
        返回:
            包含命令输出的 CompletedProcess 对象
        """
        cmd = [self.adb_path]
        
        if device_id:
            cmd.extend(["-s", device_id])
        
        cmd.extend(args)
        
        try:
            result = subprocess.run(
                cmd, 
                check=check, 
                capture_output=True, 
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"执行 ADB 命令失败: {cmd}, stderr: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            logger.error(f"执行 ADB 命令超时: {cmd}")
            raise
    
    def get_devices(self) -> List[Dict[str, str]]:
        """
        获取已连接的设备列表
        
        返回:
            设备字典列表，每个字典包含 'id' 和 'status'
        """
        result = self.execute(None, "devices", "-l")
        devices = []
        
        for line in result.stdout.splitlines()[1:]:  # 跳过第一行 "List of devices attached"
            if not line.strip():
                continue
                
            parts = line.strip().split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]
                
                device = {'id': device_id, 'status': status}
                
                # 解析额外信息
                for part in parts[2:]:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        device[key] = value
                
                devices.append(device)
        
        return devices
    
    def wait_for_device(self, device_id: str, timeout: int = 60) -> bool:
        """
        等待设备准备就绪
        
        参数:
            device_id: 设备 ID
            timeout: 超时时间（秒）
            
        返回:
            设备是否准备就绪
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # 检查设备是否在线
                devices = self.get_devices()
                device = next((d for d in devices if d['id'] == device_id), None)
                
                if device and device['status'] == 'device':
                    # 检查设备是否已经完全启动
                    boot_completed = self.execute(
                        device_id, "shell", "getprop", "sys.boot_completed",
                        timeout=5
                    )
                    
                    if "1" in boot_completed.stdout:
                        return True
            
            except Exception as e:
                logger.debug(f"等待设备时出错: {e}")
            
            time.sleep(2)
        
        return False
    
    def get_screen_size(self, device_id: str) -> Optional[Tuple[int, int]]:
        """获取设备屏幕尺寸"""
        try:
            result = self.execute(device_id, "shell", "wm", "size")
            
            # 解析输出，格式通常是 "Physical size: 1080x1920"
            match = re.search(r"(\d+)x(\d+)", result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return (width, height)
        except Exception as e:
            logger.error(f"获取屏幕尺寸失败: {e}")
        
        return None
    
    def get_current_activity(self, device_id: str) -> Optional[str]:
        """获取当前前台活动"""
        try:
            # dumpsys window 方法
            result = self.execute(
                device_id, "shell", "dumpsys", "window", "windows", "|", "grep", "-E", "'mCurrentFocus|mFocusedApp'"
            )
            
            # 解析输出寻找活动名称
            match = re.search(r"mCurrentFocus=.*?{.*\s+([\w\.]+/[\w\.]+)}", result.stdout)
            if match:
                return match.group(1)
                
            # 备用方法：使用 dumpsys activity
            result = self.execute(device_id, "shell", "dumpsys", "activity", "activities", "|", "grep", "mResumedActivity")
            match = re.search(r"mResumedActivity:.*?(\S+/\S+)", result.stdout)
            if match:
                return match.group(1)
        except Exception as e:
            logger.error(f"获取当前活动失败: {e}")
        
        return None
    
    def screenshot(self, device_id: str, local_path: Optional[str] = None) -> Optional[bytes]:
        """
        获取设备屏幕截图
        
        参数:
            device_id: 设备 ID
            local_path: 如果提供，截图将保存到此路径
            
        返回:
            图像的二进制数据，如果提供了 local_path，则返回 None
        """
        try:
            if local_path:
                # 保存到本地路径
                self.execute(device_id, "exec-out", "screencap", "-p", ">", local_path)
                return None
            else:
                # 返回图像数据
                result = self.execute(device_id, "exec-out", "screencap", "-p")
                return result.stdout.encode('latin-1')  # 处理二进制输出
        except Exception as e:
            logger.error(f"获取屏幕截图失败: {e}")
            return None
    
    def install_app(self, device_id: str, apk_path: str) -> bool:
        """安装应用"""
        try:
            self.execute(device_id, "install", "-r", apk_path)
            return True
        except Exception as e:
            logger.error(f"安装应用失败: {e}")
            return False
    
    def uninstall_app(self, device_id: str, package_name: str) -> bool:
        """卸载应用"""
        try:
            self.execute(device_id, "uninstall", package_name)
            return True
        except Exception as e:
            logger.error(f"卸载应用失败: {e}")
            return False
    
    def start_app(self, device_id: str, package_name: str, activity_name: Optional[str] = None) -> bool:
        """启动应用"""
        try:
            if activity_name:
                self.execute(device_id, "shell", "am", "start", "-n", f"{package_name}/{activity_name}")
            else:
                self.execute(device_id, "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1")
            return True
        except Exception as e:
            logger.error(f"启动应用失败: {e}")
            return False
    
    def stop_app(self, device_id: str, package_name: str) -> bool:
        """停止应用"""
        try:
            self.execute(device_id, "shell", "am", "force-stop", package_name)
            return True
        except Exception as e:
            logger.error(f"停止应用失败: {e}")
            return False
    
    def clear_app_data(self, device_id: str, package_name: str) -> bool:
        """清除应用数据"""
        try:
            self.execute(device_id, "shell", "pm", "clear", package_name)
            return True
        except Exception as e:
            logger.error(f"清除应用数据失败: {e}")
            return False
    
    def dump_ui_hierarchy(self, device_id: str, local_path: Optional[str] = None) -> Optional[str]:
        """
        转储 UI 层次结构
        
        参数:
            device_id: 设备 ID
            local_path: 如果提供，XML 将保存到此路径
            
        返回:
            XML 字符串，如果提供了 local_path，则返回 None
        """
        try:
            if local_path:
                # 转储到设备上的临时文件
                temp_file = "/sdcard/window_dump.xml"
                self.execute(device_id, "shell", "uiautomator", "dump", temp_file)
                
                # 从设备拉取文件
                self.execute(device_id, "pull", temp_file, local_path)
                
                # 删除临时文件
                self.execute(device_id, "shell", "rm", temp_file)
                
                return None
            else:
                # 转储到设备上的临时文件
                temp_file = "/sdcard/window_dump.xml"
                self.execute(device_id, "shell", "uiautomator", "dump", temp_file)
                
                # 读取文件内容
                result = self.execute(device_id, "shell", "cat", temp_file)
                
                # 删除临时文件
                self.execute(device_id, "shell", "rm", temp_file)
                
                return result.stdout
        except Exception as e:
            logger.error(f"转储 UI 层次结构失败: {e}")
            return None
