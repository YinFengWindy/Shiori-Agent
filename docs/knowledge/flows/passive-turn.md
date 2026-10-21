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
- `chat.message`：自然聊天模式中的完整已持久化消息，复用 `session.updated` 的消息载荷；立即显示但不结束回合，后续仍以 `chat.done` / `chat.error` / `chat.cancelled` 收尾。模型通过 `finish_reply.messages` 自主给出消息列表，校验后沿用序列投递；正文生成期间只透传 thinking，不展示未发送正文。
- `chat.tool.started` / `chat.tool.completed`：工具调用生命周期。
- `chat.done`：reply、thinking、tools_used、token usage 和耗时。
- `chat.error`：统一错误边界。
- `chat.cancelled`：回合被按 turn_id 取消或 bridge 关闭时的终止事件，只带 session_key 与 turn_id；按 turn_id 取消时先持久化中断回复并发 `session.updated`。

桌面普通模式与自然聊天都可在旧回复生成或连发期间通过 `chat.send` 接收补充。后端先使旧计划失效，再持久化并确认新输入，按接纳顺序等待旧回合安全收尾；不会让 RPC 等待完整模型回复。普通模式立即停止旧增量的继续发布，已展示的正文/思考前缀与已完成工具事实持久化，新一轮结合这些事实及全部已接纳输入重新回答；自然模式仅保留已发送气泡。回合发布的 `session.updated` 同样带 `turn_id`。renderer 按当前 turn 隔离终止、增量和工具状态，迟到的已发 `chat.message` 仍按持久 ID 合并，但不能回滚新回合的会话摘要。外部渠道的自动补充插话仍只在自然聊天开启时生效。

运行时多次换代时，新输入只衔接最新已接纳的前驱，形成 C → B → A 的等待链；B 即使还在等 A，也会在接纳 C 时失效，全部已接纳输入仍保留。`DesktopChatService.owns_chat_turn` 区分本代实际拥有的任务与借用的前驱；无效请求产生的借用引用不参与 owner 选择。`chat.cancel` 按 session 和 turn_id 定位实际拥有该回合的运行时，不会把借用前驱的新代当成旧任务的执行者。

输入框在回复期间可以编辑、添加附件并发送补充。无草稿时主按钮为中止；有草稿时同时保留中止和发送，手动中止不会清掉正在编辑的草稿。

## 异常分支

- BeforeTurn/BeforeReasoning abort：结束当前回合并走 abort outbound。
- Provider/reasoner 错误：生成用户可见 fallback，并保留错误 trace。
- AfterReasoning/AfterTurn 权威持久化错误：继续向边界冒泡，不能静默吞掉。
- Stream abort/timeout：停止当前 LLM stream，释放 role work，不能自动重复执行已有副作用工具。
