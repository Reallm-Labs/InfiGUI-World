#!/usr/bin/env python3
import subprocess
import os
import time

def main():
    print("===== 测试与Android模拟器的连接 =====")
    
    # ADB路径
    adb_path = "/root/.local/share/enroot/android-emulator/opt/android-sdk/platform-tools/adb"
    
    # 检查ADB路径是否存在
    if not os.path.exists(adb_path):
        print(f"错误: ADB路径不存在: {adb_path}")
        print("尝试查找可用的ADB...")
        
        # 尝试通过which查找adb
        try:
            which_result = subprocess.run(["which", "adb"], capture_output=True, text=True)
            if which_result.returncode == 0:
                adb_path = which_result.stdout.strip()
                print(f"找到ADB: {adb_path}")
            else:
                print("找不到ADB命令")
                return
        except Exception as e:
            print(f"查找ADB时出错: {e}")
            return
    
    # 启动ADB服务器
    print("\n1. 启动ADB服务器...")
    try:
        result = subprocess.run([adb_path, "start-server"], capture_output=True, text=True)
        print(f"结果: {result.returncode}")
        print(f"输出: {result.stdout}")
    except Exception as e:
        print(f"启动ADB服务器时出错: {e}")
        return
    
    # 获取设备列表
    print("\n2. 获取连接的设备...")
    try:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
        print(f"结果: {result.returncode}")
        print(f"设备列表:\n{result.stdout}")
        
        # 检查是否有设备连接
        if "device" not in result.stdout and "emulator" not in result.stdout:
            print("没有找到已连接的设备或模拟器")
            
            # 尝试在enroot环境中找到运行的模拟器
            print("\n尝试查找在enroot中运行的模拟器...")
            try:
                ps_result = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
                if "emulator" in ps_result.stdout:
                    print("找到正在运行的模拟器进程:")
                    for line in ps_result.stdout.split("\n"):
                        if "emulator" in line:
                            print(line)
                else:
                    print("没有找到正在运行的模拟器进程")
            except Exception as e:
                print(f"查找模拟器进程时出错: {e}")
    except Exception as e:
        print(f"获取设备列表时出错: {e}")
        return
    
    # 如果有设备，尝试执行一些命令
    devices = [line.split("\t")[0] for line in result.stdout.split("\n") 
              if line and "device" in line and not "List of devices" in line]
    
    if devices:
        device_id = devices[0]
        print(f"\n3. 对设备 {device_id} 执行命令...")
        
        # 获取屏幕尺寸
        try:
            result = subprocess.run(
                [adb_path, "-s", device_id, "shell", "wm", "size"], 
                capture_output=True, text=True
            )
            print(f"屏幕尺寸: {result.stdout}")
        except Exception as e:
            print(f"获取屏幕尺寸时出错: {e}")
        
        # 发送按键
        try:
            result = subprocess.run(
                [adb_path, "-s", device_id, "shell", "input", "keyevent", "KEYCODE_HOME"], 
                capture_output=True, text=True
            )
            print(f"发送HOME键: {result.returncode}")
        except Exception as e:
            print(f"发送按键时出错: {e}")
    
    print("\n===== 测试完成 =====")

if __name__ == "__main__":
    main() 