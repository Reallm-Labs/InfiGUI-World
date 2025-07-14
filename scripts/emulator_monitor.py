import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import List, Tuple


def find_adb_path() -> str:
    """Return adb executable path, try common locations and PATH."""
    default_paths = [
        os.getenv("ADB_PATH"),
        "/root/Android/Sdk/platform-tools/adb",
        "/opt/android-sdk/platform-tools/adb",
        "adb",  # rely on PATH
    ]
    for path in default_paths:
        if not path:
            continue
        if path == "adb":
            if shutil.which(path):
                return path
        elif os.path.exists(path):
            return path
    print("[ERROR] adb executable not found – please set ADB_PATH env or install platform-tools.", file=sys.stderr)
    sys.exit(1)


ADB_PATH = find_adb_path()


def run_cmd(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run command helper that captures output and returns CompletedProcess."""
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kwargs)


def get_emulator_devices() -> List[str]:
    """Return a list of device ids like ['emulator-5554', ...] detected by adb."""
    result = run_cmd([ADB_PATH, "devices"])
    lines = result.stdout.strip().split("\n")[1:]  # skip header
    device_ids = []
    for line in lines:
        if not line.strip():
            continue
        cols = line.split("\t")
        if cols and cols[0].startswith("emulator-"):
            device_ids.append(cols[0])
    return device_ids


def get_emulator_processes() -> List[Tuple[int, str]]:
    """Return list of (pid, cmdline) tuples for running emulator processes."""
    # run_cmd already sets text=True, so avoid passing it twice
    result = run_cmd(["ps", "-eo", "pid,cmd"])
    processes = []
    for line in result.stdout.strip().split("\n"):
        match = re.search(r"^\s*(\d+)\s+(.+)$", line)
        if match:
            pid = int(match.group(1))
            cmdline = match.group(2)
            if "emulator" in cmdline and "-avd" in cmdline:
                processes.append((pid, cmdline))
    return processes


def list_status():
    devices = get_emulator_devices()
    processes = get_emulator_processes()

    print("== ADB Devices ==")
    if devices:
        for d in devices:
            print(f"  {d}")
    else:
        print("  (none)")

    print("\n== Emulator Processes ==")
    if processes:
        for pid, cmd in processes:
            print(f"  PID {pid}: {cmd}")
    else:
        print("  (none)")


def kill_device(device_id: str):
    print(f"[INFO] Stopping {device_id} …")
    run_cmd([ADB_PATH, "-s", device_id, "emu", "kill"])


def kill_all():
    devices = get_emulator_devices()
    for d in devices:
        kill_device(d)

    # give adb a moment, then kill remaining qemu-system / emulator processes as fallback
    processes = get_emulator_processes()
    for pid, cmd in processes:
        print(f"[WARN] Force killing lingering emulator process pid={pid}")
        try:
            os.kill(pid, 9)
        except Exception as e:
            print(f"   → failed to kill pid {pid}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Android emulator monitor & cleanup tool")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show current emulator devices & processes")

    kill_parser = sub.add_parser("kill", help="Kill a specific emulator by device id")
    kill_parser.add_argument("device_id", help="Device id, e.g. emulator-5554")

    sub.add_parser("kill-all", help="Kill all running emulators")

    args = parser.parse_args()

    if args.command == "status":
        list_status()
    elif args.command == "kill":
        kill_device(args.device_id)
    elif args.command == "kill-all":
        kill_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 