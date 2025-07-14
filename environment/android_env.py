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
import dataclasses
from android_world.env import representation_utils as aw_repr
from android_world.env import json_action as aw_json
from environment.action_utils import to_json_action
from android_world.env import adb_utils as aw_adb_utils  # type: ignore

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
        """使用 android_world.env.representation_utils 将 UI 层次结构 XML 解析为元素列表"""
        try:
            elements = aw_repr.xml_dump_to_ui_elements(xml_data)
            # 将 dataclass 转换为普通字典，方便后续 JSON 序列化
            return [dataclasses.asdict(el) for el in elements]
        except Exception as e:
            logger.warning(f"解析 UI 元素失败: {e}")
            return []
    
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
    
    def _execute_json_action(self, device_id: str, ja: aw_json.JSONAction) -> Dict[str, Any]:
        """执行来自 android_world JSONAction 的动作并返回 observation 结果字典。"""
        try:
            action_type = ja.action_type
            ### log info here
            print('--------------------------------')
            print('action_type:', action_type)
            print('ja:', ja)
            print('--------------------------------')
            obs: Dict[str, Any] = {"action": action_type}

            if action_type in {aw_json.CLICK, aw_json.DOUBLE_TAP, aw_json.LONG_PRESS}:
                if ja.x is None or ja.y is None:
                    raise ValueError("click/press 类动作需要提供 x、y 坐标")
                x, y = int(ja.x), int(ja.y)
                # DOUBLE_TAP/LONG_PRESS 仅通过两次 tap / 长按实现，简化处理
                if action_type == aw_json.CLICK:
                    self._execute_adb_command(device_id, "shell", "input", "tap", str(x), str(y))
                elif action_type == aw_json.DOUBLE_TAP:
                    self._execute_adb_command(device_id, "shell", "input", "tap", str(x), str(y))
                    time.sleep(0.05)
                    self._execute_adb_command(device_id, "shell", "input", "tap", str(x), str(y))
                else:  # LONG_PRESS
                    self._execute_adb_command(device_id, "shell", "input", "swipe", str(x), str(y), str(x), str(y), "800")
                obs.update({"x": x, "y": y, "success": True})

            elif action_type == aw_json.INPUT_TEXT:
                if ja.text is None:
                    raise ValueError("input_text 动作需要提供 text 字段")
                text = ja.text
                # shell input text 需要处理空格
                safe_text = text.replace(" ", "%s")
                self._execute_adb_command(device_id, "shell", "input", "text", safe_text)
                obs.update({"text": text, "success": True})

            elif action_type in {aw_json.NAVIGATE_BACK, aw_json.NAVIGATE_HOME, aw_json.KEYBOARD_ENTER}:
                key_map = {
                    aw_json.NAVIGATE_BACK: "KEYCODE_BACK",
                    aw_json.NAVIGATE_HOME: "KEYCODE_HOME",
                    aw_json.KEYBOARD_ENTER: "KEYCODE_ENTER",
                }
                key_code = key_map[action_type]
                self._execute_adb_command(device_id, "shell", "input", "keyevent", key_code)
                obs.update({"key": key_code, "success": True})

            elif action_type in {aw_json.SCROLL, aw_json.SWIPE}:
                # 根据方向生成滑动坐标，使用屏幕中心或边缘
                if ja.direction is None:
                    raise ValueError("scroll/swipe 需要 direction 字段")
                direction = ja.direction.lower()
                screen_w, screen_h = self._get_screen_size(device_id) or (1080, 1920)
                mid_x, mid_y = screen_w // 2, screen_h // 2
                if direction == "down":
                    x1, y1, x2, y2 = mid_x, int(screen_h * 0.25), mid_x, int(screen_h * 0.75)
                elif direction == "up":
                    x1, y1, x2, y2 = mid_x, int(screen_h * 0.75), mid_x, int(screen_h * 0.25)
                elif direction == "left":
                    x1, y1, x2, y2 = int(screen_w * 0.75), mid_y, int(screen_w * 0.25), mid_y
                elif direction == "right":
                    x1, y1, x2, y2 = int(screen_w * 0.25), mid_y, int(screen_w * 0.75), mid_y
                else:
                    raise ValueError(f"未知方向: {ja.direction}")
                self._execute_adb_command(device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "300")
                obs.update({"direction": direction, "success": True})

            elif action_type == aw_json.OPEN_APP:
                # 打开应用：优先根据友好名称映射到 Activity；若找不到则把 app_name 当作包名处理。
                if ja.app_name is None:
                    raise ValueError("open_app 需要 app_name")

                activity: str | None = None
                activity = aw_adb_utils.get_adb_activity(ja.app_name)
                if activity:
                    # 找到匹配 Activity，使用 am start -n
                    self._execute_adb_command(
                        device_id,
                        "shell",
                        "am",
                        "start",
                        "-n",
                        activity,
                    )
                else:
                    # 回退：把 app_name 视为 package 名称，通过 monkey 简易启动
                    self._execute_adb_command(
                        device_id,
                        "shell",
                        "monkey",
                        "-p",
                        ja.app_name,
                        "1",
                    )

                obs.update({"app_name": ja.app_name, "activity": activity, "success": True})

            # ------------------------------------------------------------------
            # Generic keycode press (press_keyboard) – leverage ja.keycode field
            # ------------------------------------------------------------------
            elif ja.keycode is not None:
                # If a keycode is supplied, treat it as a single key event.
                keycode = ja.keycode
                self._execute_adb_command(device_id, "shell", "input", "keyevent", keycode)
                obs.update({"keycode": keycode, "success": True})

            # ------------------------------------------------------------------
            # ANSWER – e.g. accept incoming phone call (KEYCODE_CALL)
            # ------------------------------------------------------------------
            elif action_type == aw_json.ANSWER:
                self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_CALL")
                obs.update({"success": True})

            elif action_type == aw_json.WAIT:
                duration = float(ja.text) if ja.text else 1.0
                time.sleep(duration)
                obs.update({"wait_seconds": duration, "success": True})

            else:
                raise ValueError(f"暂不支持的 JSONAction 类型: {action_type}")

            return {"success": True, "observation": obs}
        except Exception as e:
            logger.error(f"执行 JSONAction 失败: {e}")
            return {"success": False, "error": str(e)}

    def step(self, trajectory_id: str, action: Any) -> Dict[str, Any]:
        """在Android模拟器中执行动作
        
        兼容两种动作格式:
        1. 字符串命令 (click 100 200 等)
        2. JSONAction 字典 / JSON 字符串 (与 android_world.env.json_action 格式保持一致)
        """
        try:
            # 若该 trajectory 对应的模拟器尚未激活，则尝试从快照加载
            if trajectory_id not in self.active_emulators:
                load_result = self.load(trajectory_id)
                if not load_result.get("success", False):
                    return load_result

            emulator_info = self.active_emulators[trajectory_id]
            device_id = emulator_info["device_id"]

            # --------------------------------------------------
            # 1) 优先尝试将动作解析为 JSONAction
            # --------------------------------------------------
            try:
                ja = to_json_action(action)
                return self._execute_json_action(device_id, ja)
            except Exception as json_err:  # noqa: BLE001
                logger.debug(f"to_json_action 解析失败，退回文本命令逻辑: {json_err}")

            # --------------------------------------------------
            # 2) 解析文本命令
            # --------------------------------------------------
            if not isinstance(action, str):
                return {"success": False, "error": "动作格式无效，应为字符串或 JSONAction"}

            parts = action.strip().split()
            if not parts:
                return {"success": False, "error": "空动作指令"}

            action_type = parts[0].lower()

            # ---- click ----
            if action_type == "click":
                if len(parts) >= 3:
                    x, y = int(parts[1]), int(parts[2])
                    self._execute_adb_command(device_id, "shell", "input", "tap", str(x), str(y))
                    observation = {"action": "click", "x": x, "y": y, "success": True}
                else:
                    return {"success": False, "error": "点击命令格式无效，应为: click <x> <y>"}

            # ---- swipe ----
            elif action_type == "swipe":
                if len(parts) >= 5:
                    x1, y1, x2, y2 = map(int, parts[1:5])
                    duration = parts[5] if len(parts) > 5 else "300"  # 默认 300ms
                    self._execute_adb_command(
                        device_id, "shell", "input", "swipe",
                        str(x1), str(y1), str(x2), str(y2), duration
                    )
                    observation = {
                        "action": "swipe",
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "duration": duration, "success": True,
                    }
                else:
                    return {"success": False, "error": "滑动命令格式无效，应为: swipe <x1> <y1> <x2> <y2> [duration]"}

            # ---- text ----
            elif action_type == "text":
                text = " ".join(parts[1:])
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                safe_text = text.replace(" ", "%s")
                self._execute_adb_command(device_id, "shell", "input", "text", safe_text)
                observation = {"action": "text", "text": text, "success": True}

            # ---- key ----
            elif action_type == "key":
                if len(parts) >= 2:
                    key = parts[1].lower()
                    key_code = self._get_key_code(key)
                    self._execute_adb_command(device_id, "shell", "input", "keyevent", key_code)
                    observation = {"action": "key", "key": key, "success": True}
                else:
                    return {"success": False, "error": "按键命令格式无效，应为: key <key_name>"}

            # ---- screenshot ----
            elif action_type == "screenshot":
                screenshot_data = self._take_screenshot(device_id)
                observation = {"action": "screenshot", "image": screenshot_data, "success": True}

            else:
                return {"success": False, "error": f"未知的动作类型: {action_type}"}

            # --------------------------------------------------
            # 更新模拟器状态 & 额外观察信息
            # --------------------------------------------------
            emulator_info["last_action"] = action
            emulator_info["last_action_time"] = time.time()
            observation.update(self._get_extra_observation(device_id))

            return {"success": True, "observation": observation}

        except Exception as e:  # noqa: BLE001
            logger.error(f"在 Android 模拟器中执行动作失败: {e}")
            return {"success": False, "error": str(e)}
    
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
