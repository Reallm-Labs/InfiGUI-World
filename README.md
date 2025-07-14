一、命令行启动方式（`python main.py …`）

1. Worker 进程  
   • 原生 ADB 模拟器  
     ```
     python main.py --mode worker --worker-type env --env-type android
     ```  
   • Android World (gRPC)  
     ```
     python main.py --mode worker --worker-type env --env-type android_world
     ```

2. 全功能 API 服务器（Flask）  
   ```
   python main.py --mode api --env-type android              # 或 android_world
   ```
   - 会自动启动：
     - `Coordinator`
     - `EnvironmentWorker`
     - `RewardWorker`
     - Flask HTTP Server（见下面「REST API 列表」）

3. 单机演示  
   ```
   python main.py --mode demo
   ```
   - 创建 Env / Reward Worker → 执行若干动作 → 打印奖励并清理。

----------------------------------------------------------------
二、REST API（Flask Server @ `/api/**`）

| 主题 | Method & Path | 说明 |
|------|---------------|------|
| Coordinator | `GET /api/coordinator/status` | 协调器状态 |
|  | `GET /api/coordinator/workers` | 所有 Worker 概览 |
| Worker 控制 | `POST /api/workers/<id>/start`\|`stop`\|`restart` | 启停指定 Worker |
|  | `GET /api/workers/<id>/status` | Worker 资源&健康 |
|  | `PUT /api/workers/<id>/config` | 更新 Worker 配置 |
| Env 生命周期 | `POST /api/env/create` | 新建环境，返回 `trajectory_id` |
|  | `POST /api/env/save` | 保存快照 |
|  | `POST /api/env/load` | 从快照恢复 |
|  | `POST /api/env/remove` | 删除环境+快照 |
| Env 交互 | `POST /api/env/step` | 执行动作，返回 observation |
| Reward | `POST /api/reward/calculate` | 根据轨迹计算奖励 |

请求/响应均为 JSON，典型示例见下节。

----------------------------------------------------------------
三、动作指令格式（两类环境统一支持）

1. 轻量 DSL（字符串）  
   ```
   click 120 350
   swipe 100 800 100 300          # duration 默认 300ms
   text "Hello World"
   key back|home|enter|power
   screenshot
   ```
2. Android World `JSONAction`（dict / JSON 字符串）  
   ```jsonc
   {
     "action_type": "click",
     "x": 120,
     "y": 350
   }
   ```
   可用字段同 `android_world.env.json_action`：  
   `click`·`double_tap`·`long_press`·`input_text`·`navigate_home|back`·`keyboard_enter`·`scroll|swipe`·`open_app`·`wait` 等。

后端会先尝试解析成 `JSONAction`；若失败再按 DSL 处理，保证向后兼容。

----------------------------------------------------------------
四、REST 交互 Demo

1. 新建环境  
   ```bash
   curl -X POST http://localhost:5000/api/env/create
   # => {"success":true,"trajectory_id":"1234-...","device_id":"emulator-5554"}
   ```

2. 执行动作（DSL & JSONAction 均可）  
   ```bash
   # DSL 示例
   curl -X POST http://localhost:5000/api/env/step \
        -H "Content-Type: application/json" \
        -d '{"trajectory_id":"1234-...","command":"click 120 350"}'

   # JSONAction 示例
   curl -X POST http://localhost:5000/api/env/step \
        -H "Content-Type: application/json" \
        -d '{
              "trajectory_id":"1234-...",
              "command":{
                "action_type":"input_text",
                "text":"Hello Android!"
              }
            }'
   ```

   返回字段统一包含  
   ```jsonc
   {
     "success": true,
     "observation": {
       "pixels": [...],           // 屏幕 RGB 数组（简化后）
       "ui_elements": [...],      // 已 dict 化的 UIElement 列表
       "current_activity": "com.android.settings/.Settings",
       "screen_size": [1080, 2340],
       "orientation": 0
     }
   }
   ```

3. 奖励计算  
   ```bash
   curl -X POST http://localhost:5000/api/reward/calculate \
        -H "Content-Type: application/json" \
        -d '{
              "reward_type":"rule_based",
              "trajectory_id":"1234-...",
              "trajectory_data":{...}
            }'
   ```