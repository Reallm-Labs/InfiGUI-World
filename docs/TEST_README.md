# Android Real Tasks Test Suite

This directory contains comprehensive test scripts for performing real Android tasks using the Android sandbox environment.

## 📋 Test Files Overview

### 1. `test_android_real_tasks.py`
**Comprehensive Android UI Automation Test**

- ✅ Creates and manages Android emulator instances
- ✅ Takes screenshots and saves them as PNG files
- ✅ Unlocks device and navigates to home screen
- ✅ Opens app drawer and navigates through apps
- ✅ Opens Settings app
- ✅ Opens Messages app  
- ✅ Tests text input and typing
- ✅ Tests navigation gestures (back, home, recent apps, scrolling)
- ✅ Saves and restores emulator states

### 2. `test_android_messaging.py`
**Messaging and Communication Test**

- ✅ Opens Phone/Dialer app
- ✅ Simulates making phone calls (without actually calling)
- ✅ Opens Messages/SMS app
- ✅ Composes SMS messages (without actually sending)
- ✅ Opens and browses Contacts app
- ✅ Tests UI element detection and interaction
- ✅ Tests communication app workflows

### 3. `test_adb.py`
**ADB Connectivity Test**

- ✅ Tests ADB server connectivity
- ✅ Detects connected Android devices/emulators
- ✅ Performs basic ADB commands
- ✅ Validates Android SDK setup

## 🚀 How to Run Tests

### Quick Start

```bash
# Run all tests in sequence
./run_android_tests.sh

# Run specific test only
./run_android_tests.sh basic      # Basic Android tasks
./run_android_tests.sh messaging  # Messaging tests
./run_android_tests.sh adb        # ADB connectivity only

# Show help
./run_android_tests.sh help
```

### Individual Test Execution

```bash
# Run comprehensive Android tasks test
python3 test_android_real_tasks.py

# Run messaging and communication test
python3 test_android_messaging.py

# Run ADB connectivity test
python3 test_adb.py
```

## 📋 Prerequisites

### 1. Android Environment Setup
Ensure the Android emulator environment is properly configured:

- Android SDK installed
- ADB accessible
- Android emulator available
- AVD (Android Virtual Device) created

### 2. Configuration
The tests use `config.json` for configuration. If not present, default values are used:

```json
{
  "environment": {
    "android": {
      "snapshot_dir": "/tmp/android_snapshots",
      "adb_path": "/root/.local/share/enroot/android-emulator/opt/android-sdk/platform-tools/adb",
      "emulator_path": "/root/.local/share/enroot/android-emulator/opt/android-sdk/emulator/emulator",
      "avd_name": "Pixel6_API33_x86",
      "boot_timeout": 120,
      "base_port": 5554
    }
  }
}
```

### 3. Python Dependencies
```bash
pip install -r requirements.txt
```

## 📸 Test Outputs

### Screenshots
Tests automatically capture screenshots:
- `screenshot_initial.png` - Initial emulator state
- `screenshot_settings.png` - After opening Settings
- `screenshot_final.png` - Final state

### Logs
Detailed logs are written to:
- `logs/` directory
- Console output with colored status indicators

### State Snapshots
Emulator states are saved to:
- `/tmp/android_snapshots/` (configurable)
- JSON metadata files with trajectory information

## 🎓 Understanding the Code

### Key Classes
- `AndroidTaskTester` - Main test orchestrator for basic tasks
- `AndroidMessagingTester` - Specialized for communication tests
- `AndroidEnvironment` - Core Android emulator management

### Key Methods
- `setup()` - Initialize emulator
- `take_screenshot()` - Capture screen
- `unlock_device()` - Device unlocking sequence
- `open_*_app()` - App opening strategies
- `test_*()` - Individual test implementations

This test suite demonstrates real-world Android automation capabilities and serves as a comprehensive example of how to interact with Android devices programmatically. 