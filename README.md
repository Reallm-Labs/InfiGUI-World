# Android 沙盒环境

这个项目提供了一个用于控制 Android 模拟器的沙盒环境，可以通过编程方式创建、控制和管理 Android 模拟器实例。

## 功能特性

- 创建和管理多个 Android 模拟器实例
- 通过 ADB 控制模拟器（点击、滑动、输入文本等）
- 获取屏幕截图和 UI 层次结构
- 保存和加载模拟器状态（快照）
- 提供 RESTful API 接口

## 环境要求

- Linux 操作系统
- Python 3.6+
- Android SDK 工具（ADB、模拟器等）

## 安装

1. 安装 Android SDK 依赖项：

```bash
sudo bash scripts/install_android_deps.sh
```

2. 安装 Python 依赖项：

```bash
pip install -r requirements.txt
```

## 使用方法

### 启动演示

```bash
bash run_demo.sh
```

### 启动 API 服务器

```bash
python3 -m main --mode api --host 0.0.0.0 --port 5000
```

### 通过 API 控制模拟器

1. 创建模拟器实例：

```bash
curl -X POST http://localhost:5000/api/env/create
```

2. 在模拟器上执行操作：

```bash
curl -X POST http://localhost:5000/api/env/step \
  -H "Content-Type: application/json" \
  -d '{"trajectory_id": "YOUR_TRAJECTORY_ID", "command": "click 500 500"}'
```

3. 保存模拟器状态：

```bash
curl -X POST http://localhost:5000/api/env/save \
  -H "Content-Type: application/json" \
  -d '{"trajectory_id": "YOUR_TRAJECTORY_ID"}'
```

### 运行基于 API 的 Rollout 演示

`rollout_api_demo.py` 脚本提供了一个示例，展示如何通过 HTTP API 以编程方式与 Android 环境和奖励计算服务进行交互。这模拟了一个简单的 rollout worker。

**前提条件：**

1.  **安装 `requests` 库：**
    ```bash
    pip install requests
    ```
2.  **确保 API 服务器正在运行：** API 服务器必须以注册 `EnvironmentWorker`（用于 Android）和 `RewardWorker` 的模式启动。通常可以运行：
    ```bash
    python main.py --mode api --host 0.0.0.0 --port 5000 --env-type android
    ```
    （根据您的设置需要调整参数。）

**运行演示：**

一旦 API 服务器运行，执行演示脚本：

```bash
python3 rollout_api_demo.py
```

该脚本将输出它执行的步骤，包括创建环境、执行操作、保存状态、计算奖励，最后移除环境。

## 支持的命令

- `click x y`