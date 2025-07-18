import requests
import time
import json
import argparse
import base64
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

API_SERVER_URL = "http://localhost:5000/api"

# ---------------------------
# Helper functions (reuse)
# ---------------------------

def create_env():
    try:
        r = requests.post(f"{API_SERVER_URL}/env/create")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

def step_env(trajectory_id: str, command: str):
    payload = {"trajectory_id": trajectory_id, "command": command}
    try:
        r = requests.post(f"{API_SERVER_URL}/env/step", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

def save_env(trajectory_id: str):
    try:
        r = requests.post(f"{API_SERVER_URL}/env/save", json={"trajectory_id": trajectory_id})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

def remove_env(trajectory_id: str):
    try:
        r = requests.post(f"{API_SERVER_URL}/env/remove", json={"trajectory_id": trajectory_id})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# ---------------------------
# Single rollout routine
# ---------------------------

def run_single_rollout(index: int, actions: list):

    print(f"[Worker {index}] Creating environment...")
    create_resp = create_env()
    if not create_resp.get("success"):
        print(f"[Worker {index}] Failed to create env: {create_resp.get('error')}")
        return False

    trajectory_id = create_resp.get("trajectory_id")
    device_id = create_resp.get("device_id")  # Only AndroidEnvironment returns this
    if device_id:
        print(f"[Worker {index}] device_id = {device_id}")
    success = True
    screenshot_idx = 1  # numbering screenshots per emulator

    try:
        for act in actions:
            # Execute the primary action
            resp = step_env(trajectory_id, act)
            if not resp.get("success"):
                print(f"[Worker {index}] Action failed ({act}): {resp.get('error')}")
                success = False
            # Allow a brief moment for the UI to update before taking a screenshot
            time.sleep(2)

            # Take a screenshot right after the action
            shot = step_env(trajectory_id, "screenshot")
            if not shot.get("success"):
                print(f"[Worker {index}] Screenshot failed after {act}: {shot.get('error')}")
                success = False
            else:
                # Try to save the image returned in observation.image
                img_b64 = shot.get("observation", {}).get("image")
                if img_b64:
                    try:
                        img_bytes = base64.b64decode(img_b64)
                        filename = f"emu{index}_shot_{screenshot_idx:02d}.png"
                        with open(filename, "wb") as fp:
                            fp.write(img_bytes)
                        print(f"[Worker {index}] saved {filename} ({len(img_bytes)} bytes)")
                        screenshot_idx += 1
                    except Exception as e:
                        print(f"[Worker {index}] Failed to save screenshot: {e}")
                else:
                    print(f"[Worker {index}] No image data in screenshot response")

            # Small delay to avoid overloading the backend
            time.sleep(0.5)

        save_env(trajectory_id)
    finally:
        remove_env(trajectory_id)

    print(f"[Worker {index}] Rollout {'succeeded' if success else 'failed'}")
    return success

# ---------------------------
# Parallel rollout demo entry
# ---------------------------

def main():
    parser = argparse.ArgumentParser(description="Run multiple rollout requests in parallel.")
    parser.add_argument("-n", "--num", type=int, default=3, help="Number of parallel rollouts")
    args = parser.parse_args()

    # Define different action sequences for each emulator so that their behaviors differ.
    # A screenshot is still captured automatically after each action within run_single_rollout.
    action_sets = [
        # Worker 1: open Chrome then navigate home
        [
            {"action_type": "open_app", "app_name": "chrome"},
            {"action_type": "navigate_home"},
        ],
        # Worker 2: open Settings
        [
            {"action_type": "open_app", "app_name": "settings"},
        ],
        # Worker 3: open Calculator
        [
            {"action_type": "open_app", "app_name": "camera"},
        ],
    ]

    with ThreadPoolExecutor(max_workers=args.num) as executor:
        futures = [
            executor.submit(
                run_single_rollout,
                i + 1,
                action_sets[i % len(action_sets)]  # cycle if more workers than predefined sets
            )
            for i in range(args.num)
        ]
        results = [f.result() for f in as_completed(futures)]

    successes = sum(1 for r in results if r)
    print(f"\n=== Parallel rollout summary: {successes}/{args.num} succeeded ===")

if __name__ == "__main__":
    main() 