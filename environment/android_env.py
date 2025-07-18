import os
import uuid
import time
import subprocess
import json
import base64
import re
import shutil
import threading
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
    
    # ------------------------------------------------------------------
    # Helper: ensure AVD exists locally – create it on-the-fly if absent
    # ------------------------------------------------------------------
    def _ensure_avd_exists(self):
        """若 avd 不存在，使用 avdmanager 自动创建。"""
        avd_home = os.environ.get("ANDROID_AVD_HOME") or os.path.join(os.path.expanduser("~"), ".android", "avd")
        avd_path = os.path.join(avd_home, f"{self.avd_name}.avd")

        if os.path.exists(avd_path):
            return  # 已存在

        logger.info(f"检测到 AVD '{self.avd_name}' 不存在，尝试自动创建…")

        # 尝试定位 avdmanager
        avdmanager_candidates: List[str] = []
        # 1) 显式配置
        if hasattr(self, "config") and self.config.get("avdmanager_path"):
            avdmanager_candidates.append(self.config["avdmanager_path"])

        # 2) 相对 emulator_path 推导
        try:
            sdk_root = os.path.abspath(os.path.join(self.emulator_path, os.pardir, os.pardir))
            avdmanager_candidates.append(os.path.join(sdk_root, "cmdline-tools", "latest", "bin", "avdmanager"))
            avdmanager_candidates.append(os.path.join(sdk_root, "tools", "bin", "avdmanager"))
        except Exception:
            pass

        # 3) PATH 中
        avdmanager_candidates.append("avdmanager")

        avdmanager_path = None
        for cand in avdmanager_candidates:
            if cand and (os.path.exists(cand) or shutil.which(cand)):
                avdmanager_path = cand if os.path.isabs(cand) else shutil.which(cand)
                break

        if not avdmanager_path:
            logger.error("未找到 avdmanager，可在 config['avdmanager_path'] 指定路径")
            raise RuntimeError("无法创建 AVD：未找到 avdmanager")

        # 默认 system-image – 可由 config 覆盖
        system_image = (
            self.config.get("system_image") if hasattr(self, "config") else None
        ) or "system-images;android-33;google_apis;x86_64"

        device_name = (
            self.config.get("device_name") if hasattr(self, "config") else None
        ) or "pixel_6"

        # 创建命令
        create_cmd = [
            avdmanager_path,
            "create",
            "avd",
            "-n",
            self.avd_name,
            "-k",
            system_image,
            "-d",
            device_name,
            "-c",
            "256M",
            "--force",
        ]

        try:
            logger.info("创建 AVD 命令: %s", " ".join(create_cmd))
            subprocess.run(create_cmd, check=True, input="no\n", text=True)  # --force 仍可能询问 overwrite，输入 no
            logger.info("AVD '%s' 创建成功", self.avd_name)
        except subprocess.CalledProcessError as e:
            logger.error("自动创建 AVD 失败: %s", e)
            raise RuntimeError("自动创建 AVD 失败")
    
    # ------------------------------------------------------------------
    # Cross-process claim helpers – prevent multiple workers attaching
    # ------------------------------------------------------------------
    _CLAIM_DIR = "/tmp/android_env_emulator_claims"

    def _try_claim_device(self, device_id: str) -> bool:
        """Attempt to atomically claim an emulator so that only one worker uses it.
        Return True if claim succeeds, False otherwise."""
        try:
            os.makedirs(self._CLAIM_DIR, exist_ok=True)
            lock_path = os.path.join(self._CLAIM_DIR, f"{device_id}.lock")
            # Use os.O_CREAT|os.O_EXCL for atomic create
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except Exception:
            return False

    def _release_claim(self, device_id: str):
        """Release the claim for a device (called when we stop/remove the emulator)."""
        try:
            lock_path = os.path.join(self._CLAIM_DIR, f"{device_id}.lock")
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # Helper: find an already running emulator that is not yet managed
    # ------------------------------------------------------------------
    def _find_existing_emulator(self) -> Optional[Tuple[str, int]]:
        """Return (device_id, console_port) of a running emulator we do not yet manage."""
        try:
            result = subprocess.run(
                [self.adb_path, "devices"], capture_output=True, text=True, check=True
            )
            for line in result.stdout.splitlines():
                if line.startswith("emulator-") and "device" in line:
                    try:
                        adb_port = int(line.split("\t")[0].split("-")[1])
                        console_port = adb_port - 1
                        device_id = f"emulator-{adb_port}"
                        # Skip ones we already track
                        if any(
                            emu.get("device_id") == device_id for emu in self.active_emulators.values()
                        ):
                            continue
                        # cross-process claim check
                        if self._try_claim_device(device_id):
                            return device_id, console_port
                        else:
                            continue
                    except Exception:
                        continue
        except Exception:
            pass
        return None
    
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
        # trajectory_id -> emulator_info  (populated dynamically)
        self.active_emulators: Dict[str, Dict[str, Any]] = {}

        # 锁用于并发情况下的端口分配，避免冲突。
        self._port_lock = threading.Lock()
        
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
        
        # 查找已经使用的端口（① 本进程已启动的 emulator ② adb devices 中已存在的 emulator）
        used_ports: set[int] = set()

        # ① 当前 Environment 启动的实例
        for emulator_info in self.active_emulators.values():
            port_val = emulator_info.get('port')
            if port_val is not None:
                used_ports.add(port_val)
                used_ports.add(port_val + 1)  # adb 端口

        # ② 系统中其它 emulator – 解析 adb devices 输出
        try:
            adb_list = subprocess.run(
                [self.adb_path, "devices"], capture_output=True, text=True, check=True
            )
            for line in adb_list.stdout.splitlines():
                if line.startswith("emulator-"):
                    try:
                        adb_port = int(line.split("\t")[0].split("-")[1])
                        console_port = adb_port - 1
                        used_ports.add(console_port)
                        used_ports.add(adb_port)
                    except Exception:
                        pass
        except Exception:
            # adb 可能暂未启动，忽略即可
            pass
        
        # 端口必须是偶数 (emulator console 端口)，adb 端口为 console+1
        port = base_port if base_port % 2 == 0 else base_port + 1

        while port in used_ports:
            port += 2  # 依次尝试下一个偶数端口

        return port, port + 1
    
    def _start_emulator(self, trajectory_id: str, port: int) -> Dict[str, Any]:
        """启动模拟器并等待它准备好接收命令"""
        # 确保 AVD 存在
        try:
            self._ensure_avd_exists()
        except Exception as e:
            return {"success": False, "error": str(e)}
        adb_port = port + 1
        device_id = f"emulator-{adb_port}"
        snapshot_name = f"sandbox_{trajectory_id[:8]}"
        
        logger.info(f"启动 Android 模拟器，端口: {port}，AVD: {self.avd_name}")
        
        # ---------------- 构建启动命令 -----------------
        cfg = getattr(self, "config", {})  # 从传入配置读取额外开关

        cmd = [self.emulator_path, "-avd", self.avd_name, "-port", str(port)]

        # gRPC 端口（方便后续调试/集成）
        cmd.extend(["-grpc", str(port + 1000)])

        # 启动选项按 config 开关附加（默认为 True）
        if cfg.get("no_window", True):
            cmd.append("-no-window")
        if cfg.get("no_audio", True):
            cmd.append("-no-audio")
        if cfg.get("no_boot_anim", True):
            cmd.append("-no-boot-anim")

        # 只在需要独占写入时用 -wipe-data，否则默认 -read-only 允许多实例并发
        if cfg.get("wipe_data", False):
            cmd.append("-wipe-data")
        else:
            # read_only 默认为 True，可通过 config 关闭
            if cfg.get("read_only", True):
                cmd.append("-read-only")

        # 不保存/加载快照（外部另外管理）
        if cfg.get("no_snapshot", True):
            cmd.append("-no-snapshot")

        # 加速开关：on/off，默认为 on
        accel_flag = cfg.get("accel", "on")
        cmd.extend(["-accel", accel_flag])
        
        try:
            logger.info("启动命令: %s", " ".join(cmd))

            # 将 emulator 输出写入独立日志文件，方便调试
            print(self.config.get('emulator_log_dir', '/tmp'))
            log_dir = self.config.get('emulator_log_dir', '/tmp') if hasattr(self, 'config') else '/tmp'
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, f"emulator_{trajectory_id[:8]}.log")
            log_file_handle = open(log_file_path, 'w')
            logger.info(f"Emulator stdout/stderr → {log_file_path}")

            # 捕获输出到文件；如需在终端实时查看可使用 tail -f
            emulator_process = subprocess.Popen(cmd, stdout=log_file_handle, stderr=log_file_handle)
            
            # import pdb; pdb.set_trace()
            
            # 等待模拟器启动
            start_time = time.time()
            device_ready = False
            
            while time.time() - start_time < self.boot_timeout:
                try:
                    # 检查设备是否在线
                    result = subprocess.run(
                        [self.adb_path, "devices"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    
                    if device_id in result.stdout:
                        # 检查设备是否已经完全启动
                        boot_completed = subprocess.run(
                            [self.adb_path, "-s", device_id, "shell", "getprop", "sys.boot_completed"],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        
                        if "1" in boot_completed.stdout:
                            device_ready = True
                            break
                    
                    elapsed = int(time.time() - start_time)
                    logger.info(f"等待模拟器启动中… 已用 {elapsed}s (device_id={device_id})")
                    time.sleep(5)
                except Exception as e:
                    logger.warning(f"等待模拟器启动时出错: {e}")
                    time.sleep(5)
            
            if not device_ready:
                # 超时，终止模拟器进程
                emulator_process.terminate()
                try:
                    log_file_handle.close()
                except Exception:
                    pass
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
            
            # 创建 baseline snapshot（若需要）
            self._ensure_baseline_snapshot(device_id)
            
            # 关闭日志文件句柄，避免文件描述符泄漏
            try:
                log_file_handle.flush()
            except Exception:
                pass

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
        """创建一个新的Android模拟器实例；若已存在空闲 emulator 则直接复用"""
        trajectory_id = str(uuid.uuid4())

        # --------------------------------------------------------------
        # 0) 尝试复用已经存在且尚未被管理的 emulator
        # --------------------------------------------------------------
        existing = self._find_existing_emulator()
        if existing:
            device_id, console_port = existing
            logger.info(f"复用已启动的 emulator {device_id} (console {console_port})")
            self.active_emulators[trajectory_id] = {
                "device_id": device_id,
                "port": console_port,
                "process": None,  # 无法取得外部进程句柄
                "snapshot_name": f"sandbox_{trajectory_id[:8]}",
                "status": "running",
                "created_time": time.time(),
            }
            return {"success": True, "trajectory_id": trajectory_id, "device_id": device_id}

        # --------------------------------------------------------------
        # 1) 如无可复用实例，再自行启动新 emulator
        # --------------------------------------------------------------
        
        try:
            # -------- 端口分配：加锁保证并发安全 --------
            with self._port_lock:
                port, adb_port = self._get_free_port_pair()  # port 为 console，adb_port 为 port+1
                # 预先占位，防止其他线程选到同一端口
                self.active_emulators[trajectory_id] = {
                    'device_id': f'emulator-{adb_port}',  # 使用 adb 端口
                    'port': port,
                    'process': None,
                    'snapshot_name': f'sandbox_{trajectory_id[:8]}',
                    'status': 'starting',
                    'created_time': time.time()
                }
            
            # 启动模拟器
            result = self._start_emulator(trajectory_id, port)
            
            if not result['success']:
                # 若启动失败，清理占位条目
                if trajectory_id in self.active_emulators:
                    self.active_emulators.pop(trajectory_id, None)
                return {
                    'success': False,
                    'error': result['error']
                }
            
            device_id = result['device_id']
            
            # 更新模拟器信息（先前已占位）
            self.active_emulators[trajectory_id].update({
                'device_id': device_id,
                'process': result['process'],
                'snapshot_name': result['snapshot_name'],
                'status': 'running'
            })
            
            return {
                'success': True,
                'trajectory_id': trajectory_id,
                'device_id': device_id
            }
            
        except Exception as e:
            # 若启动失败，清理占位条目
            if trajectory_id in self.active_emulators:
                self.active_emulators.pop(trajectory_id, None)
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
            device_id = f"emulator-{port + 1}"
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
                # 释放跨进程锁
                self._release_claim(device_id)
                
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

    # ------------------------------------------------------------------
    # Baseline snapshot helpers – fast reset between rollouts
    # ------------------------------------------------------------------
    _BASELINE_SNAPSHOT = "baseline_clean"

    def _ensure_baseline_snapshot(self, device_id: str):
        """Create a baseline snapshot inside the running emulator if it does not yet exist."""
        try:
            # Try to load – if succeed, nothing to do
            r = self._execute_adb_command(device_id, "emu", "avd", "snapshot", "load", self._BASELINE_SNAPSHOT)
            # If load worked we immediately quit
            if "KO:" not in r.stdout:
                return
        except Exception:
            pass  # load failed, so snapshot likely missing – we'll create below
        try:
            self._execute_adb_command(device_id, "emu", "avd", "snapshot", "save", self._BASELINE_SNAPSHOT)
            logger.info(f"Baseline snapshot '{self._BASELINE_SNAPSHOT}' created for {device_id}")
        except Exception as e:
            logger.warning(f"无法创建 baseline snapshot: {e}")

    def reset(self, trajectory_id: str) -> Dict[str, Any]:
        """Fast-reset emulator to the baseline snapshot; fallback to HOME+clear if snapshot missing."""
        if trajectory_id not in self.active_emulators:
            return {"success": False, "error": f"未知的 trajectory_id: {trajectory_id}"}
        emulator_info = self.active_emulators[trajectory_id]
        device_id = emulator_info["device_id"]
        try:
            # 尝试加载 baseline snapshot
            load_ok = False
            try:
                r = self._execute_adb_command(device_id, "emu", "avd", "snapshot", "load", self._BASELINE_SNAPSHOT)
                if "OK" in r.stdout:
                    load_ok = True
            except Exception:
                load_ok = False
            if not load_ok:
                # Snapshot 不存在 – 退化为模拟按 HOME & 清后台
                logger.info(f"baseline snapshot 不存在，使用按键方式重置 {device_id}")
                self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_HOME")
                # 清理最近应用，可能需要 root；这里简单按两次最近任务
                self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_APP_SWITCH")
                time.sleep(0.2)
                self._execute_adb_command(device_id, "shell", "input", "keyevent", "KEYCODE_HOME")
            return {"success": True}
        except Exception as e:
            logger.error(f"reset 失败: {e}")
            return {"success": False, "error": str(e)}
