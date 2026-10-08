---
title: 被动回合流程
kind: 流程说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/desktop_bridge/chat_service.py
  - apps/backend/desktop_bridge/chat_completion.py
  - apps/backend/bootstrap/runtime/dispatcher.py
  - apps/backend/agent/looping/core/processing.py
  - apps/backend/core/roles/role_runtime.py
  - apps/backend/agent/core/passive_turn/
related:
  - ../architecture/current-backend.md
---

# 被动回合流程

```mermaid
flowchart TD
  A[DesktopBridge request] --> B[DesktopChatService]
  B --> C[AgentLoop.process_direct]
  A2[Channel inbound via bus] --> B2[RuntimeDispatcher]
  B2 --> C2[AgentLoop.process_inbound]
  C --> D[derive role:{id} session]
  C2 --> D
  D --> E[RoleRuntimeRegistry.dispatch_passive_turn]
  E --> F[BeforeTurn]
  F --> G[BeforeReasoning]
  G --> H[Prompt render / input budget / tool discovery]
  H --> I[LLM provider]
  I --> J{function call?}
  J -- yes --> K[ToolExecutor + hooks]
  K --> I
  J -- no --> L[AfterReasoning]
  L --> M[parse / persist / outbound]
  M --> N[AfterTurn / TurnCommitted]
  N --> O[Session commit + bridge events]
```

`/compact` 命令在进入回合前被拦截（桌面端在 `desktop_bridge/chat_requests.py`，渠道在 `agent/looping/core/context_window.py`），走手动压缩而不是普通回合。

## 对外事件契约

- `chat.delta`：可见文本增量或 thinking 增量。
- `chat.tool.started` / `chat.tool.completed`：工具调用生命周期。
- `chat.done`：reply、thinking、tools_used、token usage 和耗时。
- `chat.error`：统一错误边界。
- `chat.cancelled`：回合被按 turn_id 取消或 bridge 关闭时的终止事件，只带 session_key 与 turn_id；按 turn_id 取消时先持久化中断回复并发 `session.updated`。

## 异常分支

- BeforeTurn/BeforeReasoning abort：结束当前回合并走 abort outbound。
- Provider/reasoner 错误：生成用户可见 fallback，并保留错误 trace。
- AfterReasoning/AfterTurn 权威持久化错误：继续向边界冒泡，不能静默吞掉。
- Stream abort/timeout：停止当前 LLM stream，释放 role work，不能自动重复执行已有副作用工具。
