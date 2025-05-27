import os
import uuid
import time
import subprocess
import json
import base64
import re
import shutil
from typing import Dict, Any, Optional, List, Tuple
from environment.base import Environment
from utils.logging import setup_logger

logger = setup_logger()

class AndroidEnvironment(Environment):
    """
    Android环境实现，通过ADB与Android模拟器交互
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.snapshot_dir = config.get('snapshot_dir', '/tmp/android_snapshots')
        # 尝试获取 emulator 和 adb 路径（允许通过 config 指定）。如果不存在则自动搜索常见位置或 PATH。
        self.emulator_path = config.get('emulator_path', '/root/Android/Sdk/emulator/emulator')
        self.adb_path = config.get('adb_path', '/root/Android/Sdk/platform-tools/adb')

        # ---- 动态查找 emulator 可执行文件 ----
        if not os.path.exists(self.emulator_path):
            alternative_emulator_paths = [
                'emulator',  # 在 PATH 中查找
                '/opt/android-sdk/emulator/emulator',
                '/root/.local/share/enroot/android-emulator/opt/android-sdk/emulator/emulator',
                '/root/Android/Sdk/emulator/emulator'
            ]
            for path in alternative_emulator_paths:
                try:
                    if os.path.exists(path) or (path == 'emulator' and shutil.which(path)):
                        self.emulator_path = path
                        logger.info(f"Using alternative emulator path: {self.emulator_path}")
                        break
                except Exception:
                    pass

        # ---- 动态查找 adb 可执行文件 ----
        #（adb 的初始值已在上方设定，这里复用并在后续段落检查是否存在）
        self.avd_name = config.get('avd_name', 'Pixel6_API33')  # 默认使用 Pixel6 API33 模拟器
        self.active_emulators = {}  # trajectory_id -> emulator_info
        
        # 额外的配置参数
        self.base_port = config.get('base_port', 5554)  # 模拟器基础端口
        self.boot_timeout = config.get('boot_timeout', 60)  # 启动超时时间（秒）
        self.dump_ui_timeout = config.get('dump_ui_timeout', 5)  # UI转储超时时间（秒）

        # 确保快照目录存在
        os.makedirs(self.snapshot_dir, exist_ok=True)
        
        # 检查 ADB 服务器 - 如果指定的路径不存在，尝试使用可能在环境中的其他路径
        if not os.path.exists(self.adb_path):
            alternative_paths = [
                'adb',  # 如果在PATH中
                '/opt/android-sdk/platform-tools/adb',
                '/root/Android/Sdk/platform-tools/adb'
            ]
            for path in alternative_paths:
                try:
                    if os.path.exists(path) or (path == 'adb' and shutil.which(path)):
                        self.adb_path = path
                        break
                except:
                    pass
        
        self._ensure_adb_server()
        
        logger.info(f"Android Environment initialized with snapshot dir: {self.snapshot_dir}")
        logger.info(f"Using Emulator path: {self.emulator_path}")
        logger.info(f"Using ADB path: {self.adb_path}")
    
    def _ensure_adb_server(self):
        """确保 ADB 服务器正在运行"""
        try:
            subprocess.run([self.adb_path, "start-server"], check=True, capture_output=True)
            logger.info("ADB 服务器已启动")
        except subprocess.CalledProcessError as e:
            logger.error(f"启动 ADB 服务器失败: {e}")
            raise RuntimeError(f"无法启动 ADB 服务器: {e}")
    
    def _execute_adb_command(self, device_id: str, *args) -> subprocess.CompletedProcess:
        """执行 ADB 命令并返回结果"""
        cmd = [self.adb_path]
        
        if device_id:
            cmd.extend(["-s", device_id])
        
        cmd.extend(args)
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"执行 ADB 命令失败: {e}, stderr: {e.stderr}")
            raise
    
    def _get_free_port_pair(self) -> Tuple[int, int]:
        """获取可用的端口对（控制台端口和 ADB 端口）"""
        base_port = self.base_port
        
        # 查找已经使用的端口
        used_ports = set()
        for emulator_info in self.active_emulators.values():
            if 'port' in emulator_info:
                used_ports.add(emulator_info['port'])
        
        # 找到第一个可用的偶数端口
        port = base_port
        while port in used_ports:
            port += 2
            
        return port, port + 1
    
    def _start_emulator(self, trajectory_id: str, port: int) -> Dict[str, Any]:
        """启动模拟器并等待它准备好接收命令"""
        device_id = f"emulator-{port}"
        snapshot_name = f"sandbox_{trajectory_id[:8]}"
        
        logger.info(f"启动 Android 模拟器，端口: {port}，AVD: {self.avd_name}")
        
        # # 构建启动命令
        # cmd = [
        #     self.emulator_path,
        #     "-avd", self.avd_name,
        #     "-port", str(port),
        #     "-no-boot-anim",  # 不显示启动动画
        #     "-no-audio",      # 禁用音频
        #     "-no-window"      # 无窗口模式
        # ]
        
        # # 如果需要创建快照，添加相关参数
        # cmd.extend(["-snapshot", snapshot_name])

        # need use shell mode to run and export env
        cmd = f"{self.emulator_path} -avd {self.avd_name} -port {port} -no-boot-anim -no-audio -no-window"
        cmd += f" --snapshot {snapshot_name}"
        
        try:
            # 启动模拟器进程
            print("create emulator cmd in Popen:", cmd)
            emulator_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            
            print("stdout of emulator process:", emulator_process.stdout.read())
            print("stderr of emulator process:", emulator_process.stderr.read())

            # import pdb; pdb.set_trace()
            
            # 等待模拟器启动
            start_time = time.time()
            device_ready = False
            
            while time.time() - start_time < self.boot_timeout:
                try:
                    # 检查设备是否在线
                    cmd = f"{self.adb_path} devices"
                    print("check device online cmd:", cmd)
                    result = subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                        shell=True
                    )
                    
                    if device_id in result.stdout:
                        # 检查设备是否已经完全启动
                        print("emulator id:", device_id)
                        cmd = f"{self.adb_path} -s {device_id} shell getprop sys.boot_completed"
                        print("check device boot completed cmd:", cmd)
                        boot_completed = subprocess.run(
                            cmd,
                            check=True,
                            capture_output=True,
                            text=True,
                            shell=True
                        )
                        
                        if "1" in boot_completed.stdout:
                            device_ready = True
                            break
                    
                    time.sleep(5)
                except Exception as e:
                    logger.warning(f"等待模拟器启动时出错: {e}")
                    time.sleep(5)
            
            if not device_ready:
                # 超时，终止模拟器进程
                emulator_process.terminate()
                try:
                    emulator_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    emulator_process.kill()
                
                return {
                    'success': False,
                    'error': f"启动模拟器超时（{self.boot_timeout}秒）"
                }
            
            # 解锁屏幕
            self._unlock_screen(device_id)
            
            return {
                'success': True,
                'device_id': device_id,
                'process': emulator_process,
                'port': port,
                'snapshot_name': snapshot_name
            }
        except Exception as e:
            logger.error(f"启动模拟器失败: {e}")
            return {
                'success': False,
                'error': f"启动模拟器失败: {str(e)}"
            }
    
    def _unlock_screen(self, device_id: str):
        """解锁模拟器屏幕"""
        try:
            # 唤醒设备
            self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
            
            # 向上滑动解锁
            screen_size = self._get_screen_size(device_id)
            if screen_size:
                width, height = screen_size
                self._execute_adb_command(
                    device_id, "shell", "input", "swipe",
                    str(width // 2), str(height * 2 // 3),
                    str(width // 2), str(height // 3),
                    "300"  # 滑动时间（毫秒）
                )
        except Exception as e:
            logger.warning(f"解锁屏幕失败（可能已经解锁）: {e}")
    
    def _get_screen_size(self, device_id: str) -> Optional[Tuple[int, int]]:
        """获取屏幕尺寸"""
        try:
            result = self._execute_adb_command(
                device_id, "shell", "wm", "size"
            )
            
            # 解析输出，格式通常是 "Physical size: 1080x1920"
            match = re.search(r"(\d+)x(\d+)", result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return (width, height)
        except Exception as e:
            logger.error(f"获取屏幕尺寸失败: {e}")
        
        return None
    
    def _stop_emulator(self, device_id: str):
        """停止模拟器"""
        try:
            # 使用 ADB 的 emu kill 命令
            self._execute_adb_command(device_id, "emu", "kill")
            logger.info(f"已停止模拟器 {device_id}")
            return True
        except Exception as e:
            logger.error(f"停止模拟器失败: {e}")
            return False
    
    def _take_screenshot(self, device_id: str) -> Optional[str]:
        """获取设备屏幕截图，返回 Base64 编码的图像数据"""
        try:
            # 在截图前先唤醒屏幕，确保不是黑屏状态
            try:
                # 唤醒设备
                self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
                # 短暂等待屏幕完全唤醒
                import time
                time.sleep(0.5)
                
                # 发送一个轻微的向上滑动来确保屏幕处于活跃状态
                screen_size = self._get_screen_size(device_id)
                if screen_size:
                    width, height = screen_size
                    # 轻微向上滑动，不会触发解锁但能保持屏幕活跃
                    self._execute_adb_command(
                        device_id, "shell", "input", "swipe",
                        str(width // 2), str(height - 100),
                        str(width // 2), str(height - 200),
                        "100"  # 短时间滑动
                    )
                    time.sleep(0.3)
            except Exception as e:
                logger.warning(f"唤醒屏幕时出现问题，继续截图: {e}")
            
            # 执行屏幕截图命令，返回二进制数据
            result = subprocess.run(
                [self.adb_path, "-s", device_id, "exec-out", "screencap", "-p"],
                check=True,
                capture_output=True  # 不要设置 text=True，保持二进制数据
            )
            
            # Base64 编码图像数据
            if result.stdout:
                return base64.b64encode(result.stdout).decode('utf-8')
        except Exception as e:
            logger.error(f"获取屏幕截图失败: {e}")
        
        return None
    
    def _dump_ui_hierarchy(self, device_id: str) -> Optional[str]:
        """获取 UI 层次结构，使用 uiautomator dump 命令"""
        try:
            # 将 XML 文件转储到临时文件
            temp_file = "/sdcard/window_dump.xml"
            
            # 首先尝试转储UI
            dump_result = self._execute_adb_command(
                device_id, "shell", "uiautomator", "dump", temp_file
            )
            
            # 等待文件创建完成
            import time
            time.sleep(0.5)
            
            # 检查文件是否存在
            check_result = subprocess.run(
                [self.adb_path, "-s", device_id, "shell", "test", "-f", temp_file],
                capture_output=True
            )
            
            if check_result.returncode != 0:
                logger.warning(f"UI转储文件不存在，尝试备用方法")
                # 尝试使用 dumpsys activity top 作为备用
                try:
                    fallback_result = self._execute_adb_command(
                        device_id, "shell", "dumpsys", "activity", "top"
                    )
                    if fallback_result.stdout:
                        return f"<activity_info>{fallback_result.stdout}</activity_info>"
                except:
                    pass
                return None
            
            # 读取内容
            result = self._execute_adb_command(
                device_id, "shell", "cat", temp_file
            )
            
            # 删除临时文件
            try:
                self._execute_adb_command(
                    device_id, "shell", "rm", temp_file
                )
            except:
                pass  # 删除失败不影响主要功能
            
            return result.stdout if result.stdout else None
            
        except Exception as e:
            logger.warning(f"转储 UI 层次结构失败，这不会影响基本功能: {e}")
        
        return None
    
    def _parse_ui_elements(self, xml_data: str) -> List[Dict[str, Any]]:
        """解析 UI 元素信息"""
        if not xml_data:
            return []
        
        elements = []
        
        # 使用正则表达式匹配节点属性
        # 这是一个简化的实现，实际上可能需要使用 XML 解析库
        pattern = r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="([^"]*)"[^>]*resource-id="([^"]*)"[^>]*class="([^"]*)"[^>]*'
        matches = re.finditer(pattern, xml_data)
        
        for match in matches:
            x1, y1, x2, y2, text, resource_id, class_name = match.groups()
            elements.append({
                'bounds': [int(x1), int(y1), int(x2), int(y2)],
                'text': text,
                'resource_id': resource_id,
                'class': class_name
            })
        
        return elements
    
    def _get_current_activity(self, device_id: str) -> Optional[str]:
        """获取当前活动"""
        try:
            # 获取窗口信息，不使用管道
            result = self._execute_adb_command(
                device_id, "shell", "dumpsys", "window", "windows"
            )
            
            # 在Python中过滤输出，寻找焦点窗口
            if result.stdout:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'mCurrentFocus' in line or 'mFocusedApp' in line:
                        # 解析输出，寻找类似 "mCurrentFocus=Window{...}"
                        import re
                        match = re.search(r'([\w\.]+/[\w\.]+)', line)
                        if match:
                            return match.group(1)
        except Exception as e:
            logger.error(f"获取当前活动失败: {e}")
        
        return None
    
    def create(self) -> Dict[str, Any]:
        """创建一个新的Android模拟器实例"""
        trajectory_id = str(uuid.uuid4())
        
        try:
            # 获取可用端口
            port, adb_port = self._get_free_port_pair()
            
            # 启动模拟器
            result = self._start_emulator(trajectory_id, port)
            
            if not result['success']:
                return {
                    'success': False,
                    'error': result['error']
                }
            
            device_id = result['device_id']
            
            # 记录模拟器信息
            self.active_emulators[trajectory_id] = {
                'device_id': device_id,
                'port': port,
                'process': result['process'],
                'snapshot_name': result['snapshot_name'],
                'status': 'running',
                'created_time': time.time()
            }
            
            return {
                'success': True,
                'trajectory_id': trajectory_id,
                'device_id': device_id
            }
            
        except Exception as e:
            logger.error(f"创建 Android 模拟器失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def save(self, trajectory_id: str) -> Dict[str, Any]:
        """保存Android模拟器状态到快照"""
        if trajectory_id not in self.active_emulators:
            return {
                'success': False,
                'error': f"未知的 trajectory_id: {trajectory_id}"
            }
        
        try:
            emulator_info = self.active_emulators[trajectory_id]
            device_id = emulator_info['device_id']
            snapshot_name = emulator_info['snapshot_name']
            
            logger.info(f"保存模拟器状态 {trajectory_id} 到快照 {snapshot_name}")
            
            # 创建快照
            self._execute_adb_command(device_id, "emu", "avd", "snapshot", "save", snapshot_name)
            
            # 保存快照元数据
            snapshot_meta_path = os.path.join(self.snapshot_dir, f"{trajectory_id}.json")
            with open(snapshot_meta_path, 'w') as f:
                json.dump({
                    'trajectory_id': trajectory_id,
                    'device_id': device_id,
                    'port': emulator_info['port'],
                    'snapshot_name': snapshot_name,
                    'timestamp': time.time()
                }, f, indent=2)
            
            emulator_info['snapshot_path'] = snapshot_meta_path
            emulator_info['status'] = 'saved'
            
            return {
                'success': True,
                'snapshot_path': snapshot_meta_path
            }
            
        except Exception as e:
            logger.error(f"保存 Android 模拟器状态失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def load(self, trajectory_id: str) -> Dict[str, Any]:
        """从快照加载Android模拟器状态"""
        # 检查快照元数据是否存在
        snapshot_meta_path = os.path.join(self.snapshot_dir, f"{trajectory_id}.json")
        
        if not os.path.exists(snapshot_meta_path):
            return {
                'success': False,
                'error': f"找不到 trajectory_id 的快照: {trajectory_id}"
            }
        
        try:
            # 如果模拟器已经在运行，先停止它
            if trajectory_id in self.active_emulators:
                emulator_info = self.active_emulators[trajectory_id]
                if emulator_info.get('status') == 'running':
                    self._stop_emulator(emulator_info['device_id'])
            
            # 加载快照元数据
            with open(snapshot_meta_path, 'r') as f:
                snapshot_data = json.load(f)
            
            # 获取可用端口（如果需要新端口）
            if trajectory_id not in self.active_emulators:
                port, adb_port = self._get_free_port_pair()
            else:
                port = self.active_emulators[trajectory_id]['port']
            
            # 启动模拟器，加载快照
            snapshot_name = snapshot_data['snapshot_name']
            
            # 构建启动命令
            cmd = [
                self.emulator_path,
                "-avd", self.avd_name,
                "-port", str(port),
                "-no-boot-anim",
                "-no-audio",
                "-no-window",
                "-snapshot", snapshot_name,
                "-snapshot-load"
            ]
            
            # 启动模拟器进程
            emulator_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待模拟器启动
            device_id = f"emulator-{port}"
            start_time = time.time()
            device_ready = False
            
            while time.time() - start_time < self.boot_timeout:
                try:
                    result = subprocess.run(
                        [self.adb_path, "devices"],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    
                    if device_id in result.stdout:
                        boot_completed = subprocess.run(
                            [self.adb_path, "-s", device_id, "shell", "getprop", "sys.boot_completed"],
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        
                        if "1" in boot_completed.stdout:
                            device_ready = True
                            break
                    
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"等待模拟器启动时出错: {e}")
                    time.sleep(2)
            
            if not device_ready:
                # 超时，终止模拟器进程
                emulator_process.terminate()
                try:
                    emulator_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    emulator_process.kill()
                
                return {
                    'success': False,
                    'error': f"从快照加载模拟器超时（{self.boot_timeout}秒）"
                }
            
            # 更新或创建模拟器信息
            self.active_emulators[trajectory_id] = {
                'device_id': device_id,
                'port': port,
                'process': emulator_process,
                'snapshot_name': snapshot_name,
                'status': 'running',
                'snapshot_path': snapshot_meta_path,
                'loaded_time': time.time()
            }
            
            return {
                'success': True,
                'device_id': device_id
            }
            
        except Exception as e:
            logger.error(f"加载 Android 模拟器状态失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def step(self, trajectory_id: str, action: str) -> Dict[str, Any]:
        """在Android模拟器中执行动作"""
        if trajectory_id not in self.active_emulators:
            # 尝试加载现有快照
            load_result = self.load(trajectory_id)
            if not load_result['success']:
                return load_result
        
        try:
            emulator_info = self.active_emulators[trajectory_id]
            device_id = emulator_info['device_id']
            
            logger.info(f"在模拟器 {device_id} 中执行动作 '{action}'")
            
            # 解析动作命令
            parts = action.split(' ')
            action_type = parts[0].lower()
            
            observation = {}
            
            if action_type == 'click':
                if len(parts) >= 3:
                    x, y = int(parts[1]), int(parts[2])
                    self._execute_adb_command(device_id, "shell", "input", "tap", str(x), str(y))
                    observation = {'action': 'click', 'x': x, 'y': y, 'success': True}
                else:
                    return {'success': False, 'error': '点击命令格式无效'}
                
            elif action_type == 'swipe':
                if len(parts) >= 5:
                    x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                    duration = parts[5] if len(parts) > 5 else "300"  # 默认滑动时间 300ms
                    self._execute_adb_command(
                        device_id, "shell", "input", "swipe", 
                        str(x1), str(y1), str(x2), str(y2), duration
                    )
                    observation = {'action': 'swipe', 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'success': True}
                else:
                    return {'success': False, 'error': '滑动命令格式无效'}
                
            elif action_type == 'text':
                # 合并剩余部分作为文本
                text = ' '.join(parts[1:])
                # 移除可能的引号
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                self._execute_adb_command(device_id, "shell", "input", "text", text)
                observation = {'action': 'text', 'text': text, 'success': True}
                
            elif action_type == 'key':
                if len(parts) >= 2:
                    key = parts[1].lower()
                    key_code = self._get_key_code(key)
                    self._execute_adb_command(device_id, "shell", "input", "keyevent", key_code)
                    observation = {'action': 'key', 'key': key, 'success': True}
                else:
                    return {'success': False, 'error': '按键命令格式无效'}
                
            elif action_type == 'screenshot':
                # 获取屏幕截图
                screenshot_data = self._take_screenshot(device_id)
                observation = {'action': 'screenshot', 'image': screenshot_data, 'success': True}
                
            else:
                return {'success': False, 'error': f'未知的动作类型: {action_type}'}
            
            # 更新模拟器状态
            emulator_info['last_action'] = action
            emulator_info['last_action_time'] = time.time()
            
            # 获取额外的观察信息
            extra_observation = self._get_extra_observation(device_id)
            observation.update(extra_observation)
            
            return {
                'success': True,
                'observation': observation
            }
            
        except Exception as e:
            logger.error(f"在 Android 模拟器中执行动作失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_key_code(self, key: str) -> str:
        """将关键字转换为 Android 键代码"""
        key_mapping = {
            'back': 'KEYCODE_BACK',
            'home': 'KEYCODE_HOME',
            'menu': 'KEYCODE_MENU',
            'power': 'KEYCODE_POWER',
            'enter': 'KEYCODE_ENTER',
            'delete': 'KEYCODE_DEL',
            'recents': 'KEYCODE_APP_SWITCH',
            'volume_up': 'KEYCODE_VOLUME_UP',
            'volume_down': 'KEYCODE_VOLUME_DOWN'
        }
        
        return key_mapping.get(key.lower(), key)
    
    def remove(self, trajectory_id: str) -> Dict[str, Any]:
        """删除Android模拟器实例和快照"""
        # 首先检查快照文件
        snapshot_meta_path = os.path.join(self.snapshot_dir, f"{trajectory_id}.json")
        snapshot_exists = os.path.exists(snapshot_meta_path)
        
        # 检查激活的模拟器
        emulator_active = trajectory_id in self.active_emulators
        
        if not snapshot_exists and not emulator_active:
            return {'success': False, 'error': f"未知的 trajectory_id: {trajectory_id}"}
        
        try:
            # 如果模拟器在运行，停止它
            if emulator_active:
                emulator_info = self.active_emulators[trajectory_id]
                device_id = emulator_info['device_id']
                
                logger.info(f"移除模拟器实例和快照 {trajectory_id}")
                
                # 停止模拟器
                if emulator_info['status'] == 'running':
                    self._stop_emulator(device_id)
                
                # 如果有进程引用，尝试终止
                if 'process' in emulator_info and emulator_info['process']:
                    try:
                        emulator_info['process'].terminate()
                        emulator_info['process'].wait(timeout=5)
                    except:
                        # 如果无法正常终止，强制终止
                        try:
                            emulator_info['process'].kill()
                        except:
                            pass
                
                # 从激活模拟器列表中删除
                del self.active_emulators[trajectory_id]
            
            # 删除快照文件
            if snapshot_exists:
                # 读取快照元数据以获取快照名称
                try:
                    with open(snapshot_meta_path, 'r') as f:
                        meta_data = json.load(f)
                        snapshot_name = meta_data.get('snapshot_name')
                        
                    # 实际上，我们不能通过 ADB 直接删除模拟器快照
                    # 在生产环境中，可能需要使用 Android Studio 或特定 API 删除快照
                    # 这里只删除元数据文件
                    os.remove(snapshot_meta_path)
                except Exception as e:
                    logger.warning(f"删除快照元数据时出错: {e}")
            
            return {
                'success': True,
                'message': f"已移除相关的模拟器和快照"
            }
            
        except Exception as e:
            logger.error(f"删除 Android 模拟器失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_extra_observation(self, device_id: str) -> Dict[str, Any]:
        """获取额外的观察信息"""
        result = {}
        
        try:
            # 获取当前活动
            current_activity = self._get_current_activity(device_id)
            if current_activity:
                result['current_activity'] = current_activity
            
            # 获取屏幕尺寸
            screen_size = self._get_screen_size(device_id)
            if screen_size:
                result['screen_size'] = screen_size
            
            # 获取 UI 层次结构
            ui_xml = self._dump_ui_hierarchy(device_id)
            if ui_xml:
                ui_elements = self._parse_ui_elements(ui_xml)
                result['ui_elements'] = ui_elements
        except Exception as e:
            logger.error(f"获取额外观察信息失败: {e}")
        
        return result
