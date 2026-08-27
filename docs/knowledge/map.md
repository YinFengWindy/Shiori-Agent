---
title: Shiori 能力地图
kind: 能力地图
status: 当前有效
last_verified_commit: f59ad966
source_paths:
  - apps/backend/bootstrap/wiring.py
  - apps/backend/core/
  - apps/backend/agent/
  - apps/backend/proactive_v2/
  - apps/backend/plugins/
  - apps/backend/desktop_bridge/
related:
  - index.md
  - architecture/overview.md
---

# Shiori 能力地图

| 领域 | Owning module | 主要下游 |
| --- | --- | --- |
| 应用启动与装配 | `apps/backend/main.py`、`apps/backend/bootstrap/app.py`、`apps/backend/bootstrap/wiring.py` | 渠道、Agent、角色运行时、主动循环、桌面桥接 |
| 角色聚合 | `apps/backend/core/roles/store.py`、`apps/backend/core/roles/services.py`、`apps/backend/core/roles/role_runtime.py` | 会话绑定、关系、记忆、主动行为、桌面 UI |
| 关系与场景 | `apps/backend/core/roles/relationship_runtime/`、`apps/backend/core/roles/scene_followup_runtime.py` | 心情/寂寞、主动触发、场景追问、自动 CG |
| 会话 | `apps/backend/session/` | Agent 回合、在线状态、消息历史、搜索 |
| 对话持久化 | `apps/backend/conversation/` | 线程投影、旧数据迁移、跨入口消息连续性 |
| 记忆契约 | `apps/backend/core/memory/` | Agent 检索与生命周期插件 |
| 默认与增强记忆 | `apps/backend/plugins/default_memory/`、`apps/backend/memory2/` | 查询改写、召回、注入规划、响应后写入 |
| 主动行为 | `apps/backend/proactive_v2/` | 传感、裁定、Agent tick、投递、状态持久化 |
| Drift | `apps/backend/agent/core/drift_turn.py`、`apps/backend/proactive_v2/drift_state.py` | 特殊回合、工具、主动状态 |
| NovelAI | `apps/backend/core/integrations/novelai/` | 手动图片生成、自动 CG、桌面图片面板 |
| 自动 CG | `apps/backend/plugins/novelai/` | 场景判断、生成、消息推送、权威角色会话 |
| 渠道 | `apps/backend/infra/channels/`、`apps/backend/core/channels/hub.py`、`apps/backend/plugins/qqbot/` | 消息总线、会话定位、媒体发送 |
| Agent 回合 | `apps/backend/agent/core/`、`apps/backend/agent/turns/`、`apps/backend/agent/lifecycle/` | 上下文、推理、工具、输出、生命周期事件 |
| 工具、插件、MCP | `apps/backend/agent/tools/`、`apps/backend/agent/plugins/`、`apps/backend/agent/mcp/` | ToolRegistry、ToolExecutor、远端工具连接 |
| 调度任务 | `apps/backend/agent/scheduler.py`、`apps/backend/agent/tools/schedule.py`、`apps/backend/desktop_bridge/schedule_role_task_service.py` | 主动触发、角色任务、桌面展示 |
| 桌面桥接 | `apps/backend/desktop_bridge/` | Electron 主进程、React renderer、后端服务 |
| 桌面界面 | `apps/desktop/src/`、`apps/desktop/renderer/src/` | 角色管理、聊天、设置、图片、任务 |
| 单角色剧情 | `apps/backend/story_simulation/`、`apps/backend/desktop_bridge/story_simulation_handler.py`、`apps/desktop/renderer/src/story/` | 剧情事实、角色/玩家快照、提交事件、固定故事日期与“清晨/上午/下午/夜晚/深夜”五段时段时钟、桌面剧情界面 |
| 桌宠语音 | `apps/desktop/src/voice/`、`apps/desktop/renderer/src/voice/`、`apps/backend/desktop_bridge/voice/voice_service.py`、`apps/backend/desktop_bridge/voice/tts_coordinator.py` | 录音、ASR、角色 Loop、按句 TTS、播放与中断 |

```mermaid
flowchart LR
    Channel["渠道 / 桌面端"] --> Bus["消息总线"]
    Bus --> Session["Session / Conversation"]
    Session --> Agent["Agent 回合"]
    Role["角色运行时"] --> Agent
    Memory["记忆"] --> Agent
    Agent --> Tools["工具 / 插件 / MCP"]
    Agent --> Output["输出分发"]
    Proactive["Proactive / Drift"] --> Agent
    Relationship["关系 / 场景"] --> Proactive
    Relationship --> AutoCG["自动 CG"]
    AutoCG --> NovelAI["NovelAI"]
    NovelAI --> Output
    Output --> Channel
```
