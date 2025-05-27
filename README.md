# InfiGUI-World

A comprehensive framework for Android emulator automation and GUI interaction, designed for agentic environments and autonomous GUI testing. This project provides a scalable sandbox environment for controlling Android emulators programmatically with support for screenshots, UI hierarchy analysis, and reward-based evaluation.

## 🚀 Features

- **Multi-Emulator Management**: Create and manage multiple Android emulator instances concurrently
- **ADB Integration**: Full ADB support for device control (clicks, swipes, text input, key events)
- **Visual Monitoring**: Capture screenshots and analyze UI hierarchy structure
- **State Management**: Save and restore emulator snapshots for reproducible testing
- **RESTful API**: Complete HTTP API for remote control and automation
- **Reward System**: Built-in reward calculation for reinforcement learning scenarios
- **Worker Architecture**: Distributed worker system for scalable operations
- **Trajectory Management**: Track and manage interaction sequences with unique trajectory IDs

## 📋 Requirements

- **Linux Operating System** (tested on Ubuntu)
- **Python 3.6+**
- **Android SDK Tools** (ADB, Emulator)
- **Java 11+** (for Android SDK)

## 🛠️ Installation

### 1. Install Android SDK Dependencies

```bash
sudo bash scripts/install_android_deps.sh
```

This script will:
- Install required system packages (Java 11, graphics libraries)
- Download and setup Android SDK command-line tools
- Install platform tools, emulator, and system images
- Create a default Pixel 6 API 33 AVD

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

## 🎯 Quick Start

### Run Demo

Experience the framework with a built-in demonstration:

```bash
bash run_android.sh
```

Or run the Python demo directly:

```bash
python3 main.py --mode demo
```

### Start API Server

Launch the HTTP API server for remote control:

```bash
python3 main.py --mode api --host 0.0.0.0 --port 5000
```

## 📡 API Usage

### Environment Management

**Create Environment Instance:**
```bash
curl -X POST http://localhost:5000/api/env/create
```

**Execute Actions:**
```bash
curl -X POST http://localhost:5000/api/env/step \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "YOUR_TRAJECTORY_ID",
    "command": "click 500 500"
  }'
```

**Save Environment State:**
```bash
curl -X POST http://localhost:5000/api/env/save \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "YOUR_TRAJECTORY_ID"
  }'
```

**Load Environment State:**
```bash
curl -X POST http://localhost:5000/api/env/load \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "YOUR_TRAJECTORY_ID"
  }'
```

**Remove Environment:**
```bash
curl -X POST http://localhost:5000/api/env/remove \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "YOUR_TRAJECTORY_ID"
  }'
```

### Reward Calculation

**Calculate Trajectory Reward:**
```bash
curl -X POST http://localhost:5000/api/reward/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "YOUR_TRAJECTORY_ID",
    "reward_type": "rule_based",
    "trajectory_data": {
      "actions": ["click 100 200", "swipe 100 200 300 400"],
      "states": [...],
      "success": true
    }
  }'
```

## 🎮 Supported Commands

The framework supports various interaction commands:

- **`click x y`** - Tap at coordinates (x, y)
- **`swipe x1 y1 x2 y2`** - Swipe from (x1, y1) to (x2, y2)
- **`text "message"`** - Input text string
- **`key <keyname>`** - Press key (back, home, menu, etc.)
- **`screenshot`** - Capture current screen
- **`scroll up|down|left|right`** - Scroll in specified direction

## 🏗️ Architecture

### Core Components

- **`main.py`** - Entry point supporting multiple operation modes
- **`coordinator.py`** - Central coordinator for worker management
- **`api_server.py`** - HTTP API server with Flask
- **`environment/android_env.py`** - Android emulator environment implementation
- **`worker/`** - Worker implementations for distributed processing
  - `env_worker.py` - Environment interaction worker
  - `reward_worker.py` - Reward calculation worker
  - `nginx_worker.py` - Nginx worker for load balancing

### Configuration

The framework uses `config.json` for configuration:

```json
{
  "max_workers": 5,
  "port": 5000,
  "environment": {
    "android": {
      "snapshot_dir": "/tmp/android_snapshots",
      "adb_path": "/path/to/adb",
      "emulator_path": "/path/to/emulator",
      "avd_name": "Pixel6_API33",
      "boot_timeout": 120,
      "base_port": 5554
    }
  }
}
```

## 🧪 Running Tests

Execute the comprehensive test suite:

```bash
bash run_android_tests.sh
```

Or run specific test files:

```bash
python3 test_android_real_tasks.py
python3 test_android_messaging.py
python3 test_adb.py
```

## 🔬 API Demo

The `rollout_api_demo.py` script demonstrates programmatic interaction with the API:

```bash
python3 rollout_api_demo.py
```

This demo shows:
1. Environment creation
2. Action execution
3. State saving
4. Reward calculation
5. Environment cleanup

## 🚀 Advanced Usage

### Multiple Operation Modes

- **`coordinator`** - Run as central coordinator
- **`worker`** - Run as distributed worker
- **`api`** - Run API server with integrated workers
- **`demo`** - Run interactive demonstration

### Worker Types

- **`env`** - Environment interaction worker
- **`nginx`** - Load balancing worker
- **`reward`** - Reward calculation worker

### Example Commands

```bash
# Run as coordinator only
python3 main.py --mode coordinator

# Run as environment worker
python3 main.py --mode worker --worker-type env --env-type android

# Run API server with custom configuration
python3 main.py --mode api --config custom_config.json --host 0.0.0.0 --port 8080
```

## 🔧 Development

### Project Structure

```
InfiGUI-World/
├── main.py                    # Main entry point
├── config.json               # Configuration file
├── api_server.py             # HTTP API server
├── coordinator.py            # Worker coordinator
├── environment/              # Environment implementations
│   ├── android_env.py        # Android environment
│   └── base.py              # Base environment class
├── worker/                   # Worker implementations
│   ├── env_worker.py        # Environment worker
│   ├── reward_worker.py     # Reward worker
│   └── nginx_worker.py      # Nginx worker
├── scripts/                  # Installation and setup scripts
├── utils/                    # Utility modules
└── tests/                    # Test files
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 🤝 Support

For questions, issues, or contributions, please:

1. Check existing GitHub issues
2. Create a new issue with detailed description
3. Join our community discussions

## 🔗 Related Projects

- [Android SDK](https://developer.android.com/studio/command-line)
- [ADB Documentation](https://developer.android.com/studio/command-line/adb)
- [Flask API Framework](https://flask.palletsprojects.com/)

---

**InfiGUI-World** - Empowering autonomous GUI interaction through intelligent automation frameworks.
