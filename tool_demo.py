# rollout_open_chrome_demo.py
import time
import requests
import base64
import os

API = "http://localhost:5000/api"

def create_env():
    r = requests.post(f"{API}/env/create")
    r.raise_for_status()
    data = r.json()
    assert data.get("success"), f"Create failed: {data}"
    return data["trajectory_id"]

def step_env(tid, command):
    """helper that sends a command (string or dict) to backend and returns response."""
    payload = {"trajectory_id": tid, "command": command}
    r = requests.post(f"{API}/env/step", json=payload)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        print(f"✗ step '{command}' failed: {data.get('error')}")
    return data

def save_env(tid):
    r = requests.post(f"{API}/env/save", json={"trajectory_id": tid})
    r.raise_for_status()

def remove_env(tid):
    requests.post(f"{API}/env/remove", json={"trajectory_id": tid}).close()

def main():
    print("=== rollout: open Chrome demo ===")
    tid = create_env()
    print("trajectory_id =", tid)

    # 使用 JSONAction 序列演示：打开 Chrome → 截图 → 返回主屏 → 截图
    actions_with_wait = [
        # 确保在主屏
        ({"action_type": "navigate_home"}, 1.0),
        # 直接启动 Chrome
        ({"action_type": "open_app", "app_name": "chrome"}, 3.0),
        # 返回主屏相当于关闭 Chrome
        ({"action_type": "navigate_home"}, 1.0),
    ]

    screenshot_idx = 1  # 用于命名文件

    for cmd, wait_sec in actions_with_wait:
        # 执行动作
        step_env(tid, cmd)
        time.sleep(wait_sec)
        # 紧接着截图
        obs = step_env(tid, "screenshot")
        img_b64 = obs.get("observation", {}).get("image")
        if img_b64:
            try:
                img_bytes = base64.b64decode(img_b64)
                filename = f"screenshot_{screenshot_idx:02d}.png"
                with open(filename, "wb") as fp:
                    fp.write(img_bytes)
                print(f"saved {filename} ({len(img_bytes)} bytes)")
                screenshot_idx += 1
            except Exception as e:
                print(f"✗ failed to save screenshot: {e}")
        else:
            print("✗ screenshot data missing in response")
        time.sleep(0.5)  # 给截图与下一步留一点缓冲

    # 保存并清理环境
    save_env(tid)
    remove_env(tid)
    print("=== demo done ===")

if __name__ == "__main__":
    main()