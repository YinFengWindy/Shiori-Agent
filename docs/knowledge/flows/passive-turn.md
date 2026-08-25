---
title: 被动回合流程
kind: 流程说明
status: 迁移前基线
related:
  - ../architecture/current-backend.md
---

# 被动回合流程

```mermaid
flowchart TD
  A[DesktopBridge request] --> B[DesktopChatService]
  B --> C[AgentLoop.process_direct]
  C --> D[derive role:{id} session]
  D --> E[RoleRuntimeRegistry.dispatch_passive_turn]
  E --> F[BeforeTurn]
  F --> G[BeforeReasoning]
  G --> H[Prompt render / tool discovery]
  H --> I[LLM provider]
  I --> J{function call?}
  J -- yes --> K[ToolExecutor + hooks]
  K --> I
  J -- no --> L[AfterReasoning]
  L --> M[parse / persist / outbound]
  M --> N[AfterTurn / TurnCommitted]
  N --> O[Session commit + bridge events]
```

## 对外事件契约

- `chat.delta`：可见文本增量或 thinking 增量。
- `chat.tool.started` / `chat.tool.completed`：工具调用生命周期。
- `chat.done`：reply、thinking、tools_used、token usage 和耗时。
- `chat.error`：统一错误边界。

## 异常分支

- BeforeTurn/BeforeReasoning abort：结束当前回合并走 abort outbound。
- Provider/reasoner 错误：生成用户可见 fallback，并保留错误 trace。
- AfterReasoning/AfterTurn 权威持久化错误：继续向边界冒泡，不能静默吞掉。
- Stream abort/timeout：停止当前 LLM stream，释放 role work，不能自动重复执行已有副作用工具。
