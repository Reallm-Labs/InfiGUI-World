# Project Structure

这个文档描述了重组后的Android沙盒项目的目录结构。

## 根目录结构

```
android_sandbox/
├── api/                    # API服务器和协调器
│   ├── api_server.py      # Flask HTTP API服务器
│   ├── coordinator.py     # 中央协调器，管理所有Worker
│   └── rollout_api_demo.py # API使用演示脚本
├── docs/                   # 项目文档
│   ├── FIXES_SUMMARY.md   # 修复总结文档
│   ├── TEST_README.md     # 测试说明文档
│   └── PROJECT_STRUCTURE.md # 本文档
├── environment/            # 环境实现
│   ├── android_env.py     # Android环境实现
│   └── base.py           # 环境基类定义
├── examples/              # 示例代码（空目录）
├── scripts/               # 脚本文件
│   ├── install_android_deps.sh     # 安装Android依赖
│   ├── run_android.sh              # 运行Android演示
│   ├── run_android_tests.sh        # 运行测试套件
│   └── start_android_emulator.sh   # 启动Android模拟器
├── tests/                 # 测试文件
│   ├── test_adb.py               # ADB功能测试
│   ├── test_android_messaging.py # Android消息测试
│   └── test_android_real_tasks.py # Android真实任务测试
├── utils/                 # 工具类和辅助函数
│   ├── adb_utils.py      # ADB工具函数
│   ├── config.py         # 配置管理
│   └── logging.py        # 日志设置
├── worker/                # Worker实现
│   ├── base.py           # Worker基类
│   ├── env_worker.py     # 环境Worker
│   ├── nginx_worker.py   # Nginx Worker
│   └── reward_worker.py  # 奖励计算Worker
├── .gitignore            # Git忽略文件
├── README.md             # 项目主文档
├── config.json           # 项目配置文件
└── main.py              # 项目入口文件
```

## 目录说明

### `/api/` - API和协调服务
包含项目的API服务器和协调器代码：
- `api_server.py`: Flask-based HTTP API服务器，提供RESTful接口
- `coordinator.py`: 中央协调器，负责管理和协调所有Worker
- `rollout_api_demo.py`: API使用的演示脚本

### `/docs/` - 文档
包含项目的各种文档：
- `FIXES_SUMMARY.md`: 修复和更新的总结
- `TEST_README.md`: 测试相关的说明
- `PROJECT_STRUCTURE.md`: 项目结构说明（本文档）

### `/environment/` - 环境实现
包含环境相关的核心代码：
- `android_env.py`: Android环境的具体实现
- `base.py`: 环境的基类和接口定义

### `/scripts/` - 脚本工具
包含项目的各种脚本工具：
- `install_android_deps.sh`: 安装Android SDK和依赖
- `run_android.sh`: 运行Android演示
- `run_android_tests.sh`: 运行完整的测试套件
- `start_android_emulator.sh`: 启动Android模拟器

### `/tests/` - 测试代码
包含项目的所有测试文件：
- `test_adb.py`: ADB连接和基本功能测试
- `test_android_messaging.py`: Android消息传递测试
- `test_android_real_tasks.py`: Android实际任务测试

### `/utils/` - 工具模块
包含通用的工具类和辅助函数：
- `adb_utils.py`: ADB相关的工具函数
- `config.py`: 配置文件管理
- `logging.py`: 日志系统设置

### `/worker/` - Worker实现
包含不同类型的Worker实现：
- `base.py`: Worker的基类定义
- `env_worker.py`: 环境操作Worker
- `nginx_worker.py`: Nginx负载均衡Worker
- `reward_worker.py`: 奖励计算Worker

## 主要改进

1. **更清晰的分类**: 将相关功能的文件组织到同一目录下
2. **分离关注点**: API、测试、文档、脚本等分别放在不同目录
3. **易于维护**: 新的结构使得代码更容易定位和维护
4. **标准化**: 遵循常见的Python项目结构约定

## 使用说明

重组后的项目结构保持了原有的功能，但使用时需要注意：

1. 运行脚本时需要使用新的路径：
   ```bash
   bash scripts/run_android.sh
   bash scripts/run_android_tests.sh
   ```

2. 运行测试时使用新的路径：
   ```bash
   python3 tests/test_adb.py
   ```

3. API演示脚本的新位置：
   ```bash
   python3 api/rollout_api_demo.py
   ```

4. 主入口文件保持不变：
   ```bash
   python3 main.py --mode demo
   ``` 