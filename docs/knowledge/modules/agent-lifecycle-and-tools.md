---
title: Agent 生命周期、工具、插件与 MCP
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/agent/core/
  - apps/backend/agent/turns/
  - apps/backend/agent/lifecycle/
  - apps/backend/agent/tools/
  - apps/backend/agent/plugin_host/
  - apps/backend/agent/mcp/
  - apps/backend/core/compaction.py
  - plugins/screen_perception/backend/
  - plugins/herdr/backend/
  - packages/sdk/python/shiori_sdk/background_results.py
related:
  - memory.md
  - proactive-and-drift.md
  - architecture/overview.md
---

# Agent 生命周期、工具、插件与 MCP

## 回合生命周期

被动回合由 `apps/backend/agent/core/passive_turn/` 组织（`pipeline.py` 串起各 phase，`reasoning_loop.py` / `reasoner.py` 执行推理与工具循环），主动回合在 `agent/core/proactive_turn/`。`apps/backend/agent/turns/` 的 `orchestrator.py` 负责回合协调、权威会话写入与出站分发（`outbound.py`）。生命周期模块（`agent/lifecycle/phases/`）提供 `BeforeTurn`、`BeforeReasoning`、prompt render、`BeforeStep`、`AfterStep`、`AfterReasoning`、`AfterTurn` 等 phase，使记忆、插件、自动 CG 和观测逻辑在明确边界接入；插件贡献的 phase 模块由插件内核按 slot 收集后并入默认模块链。

上下文压缩（#64）也在被动回合内完成：`passive_turn/compaction.py` 在请求超出预算时调用 `core/compaction.py` 的 `CompactionController` 生成工作摘要，当前输入和进行中的工具交换保持完整；`passive_turn/context_window.py` 提供不执行回合的预算查看与手动压缩。预算依据模型注册里的 `model_context_window`（可选 `model_auto_compact_token_limit` 作为单模型自动压缩阈值，须小于窗口），窗口缺失的注册视为未完成、需要用户补全。

## 工具体系

`ToolRegistry`（`agent/tools/registry.py`）保存工具和索引视图，`search_backend.py` 的关键词后端配合 `tool_search` 工具支持按需发现工具。`agent/tools/execution.py` 的 `ToolExecutor` 执行调用：经本代插件内核发 `ToolCalling`（插件可改参或否决，fail_closed），再跑核心链后校验（外部上下文受限回合的准入与 `agent/tools/shell/guard.py` 的最小破坏性命令拦截，D11），执行工具后发 `ToolCalled`（插件可改写结果）。文件、Shell、消息推送与历史查询、记忆、调度、网页抓取与搜索、subagent（`spawn`）、群环境与群旁听、成员查询、账号投递（`account_*`）、MCP 管理等能力都是 `agent/tools/` 下的具体工具实现；图片生成等能力由插件注册（如 `plugins/novelai/`）。

工具搜索的目的是控制可见工具规模；初始可见集合由 always-on 工具加会话历史中已发现的工具组成（`passive_turn/tool_visibility.py`），搜索结果进入当前回合，不应永久污染全局 registry。外部上下文（群聊、陌生私聊）中非已绑定用户触发的受限回合只能使用注册时声明 `external_allowed` 的工具，可附带参数取值限制，规则在 `agent/tools/external_access.py` 与 `ToolRegistry.external_denial`。后台 Shell 任务由 `agent/tools/shell/background.py` 管理注册、轮询和停止。

`observe_screen` 由独立的「24h视奸插件」（`plugins/screen_perception/`）注册，启用时桌面、Telegram、QQ 等渠道的当前角色均可使用。插件按需捕获主屏并调用角色配置的视觉模型，只向角色返回经过过滤的活动摘要，不执行桌面动作。停用时撤销工具并取消活动分析；不依赖桌宠或 `observe` 遥测插件。持续感知扩展由 #292 承接。

## 插件与 MCP

插件包位于顶层 `plugins/<id>/`（`manifest.yaml` + `backend/`、`ui/` 等子目录），对外 API 由 `packages/sdk/python/shiori_sdk/` 提供。宿主侧 `apps/backend/agent/plugin_host/` 的 `PluginKernel` 负责插件发现与准入、manifest 解析、依赖加载、setup 装配、失败回滚和卸载；能力（工具、渠道、账号、后台任务、bot 命令等）经 capabilities 与作用域服务暴露给插件。插件的工具前后处理用 `ctx.on(ToolCalling / ToolCalled, …)` 直接挂在内核事件上；插件工具经 `agent/tools/plugin_capability.py` 注册进 ToolRegistry，插件渠道、头像缓存与账号登记分别由 `core/channels/plugin_capability.py`、`core/accounts/plugin_capability.py` 实现，插件会话操作由 `session/plugin_capability.py` 实现，角色与模型、场景观测需求分别由 `core/roles/plugin_capability.py`、`core/scene/plugin_capability.py` 实现，本机进程由 `infra/process/plugin_capability.py` 实现，记忆插件接口由 `bootstrap/memory_capabilities.py`、宿主资源由 `bootstrap/plugin_capability.py` 实现，外部回合、后台结果与 bot 命令分别由 `conversation/external_turns.py`、`conversation/background_results.py`、`conversation/plugin_capability.py` 实现，插件后台任务由 `core/common/plugin_capability.py` 实现，主动 gate 由 `agent/core/proactive_turn/plugin_capability.py` 实现（P3 删除），插件事件订阅（`ScopedEventBus`）由 `bus/plugin_capability.py`、插件 RPC 登记由 `desktop_bridge/plugin_capability.py` 实现，RPC 注册表由 bootstrap 每代创建一份并经 `host.bridge` 交给内核；这些都由核心模块经 `plugin_host/core_keys.py` 的 Key 提供给装配层。`apps/backend/agent/mcp/registry.py`（`McpServerRegistry`，持久化到 `mcp_servers.json`）与 `client.py` 管理 MCP server 配置和 stdio 连接，并把远端工具同步到 ToolRegistry；`manage_tools.py` 提供 `mcp_add` / `mcp_remove` / `mcp_list` 工具。

`plugins/herdr/` 的 `herdr_start_task` 把完整需求写入 UTF-8 文件，连接明确的本机 Herdr session（CLI 和服务端均要求 >=0.9.4），在独立 worktree 以 Full Access 启动 Codex 或 Claude Code。`TaskService` 保留本进程任务记录；`delivery.py` 校验本回合结果、实际验证命令、干净提交和开放 Draft PR 的 head SHA。CLI 超时不会重发任务，Herdr 的 idle/done 不等于业务完成；工作中的终端只读取可见屏幕，日志读取失败不终止任务追踪。

通用 `background_results` capability 在真实用户工具回合捕获原角色、线程、发送者与渠道投递元数据；`HostBackgroundResults` 在角色串行 gate 内重新检查会话和绑定，经 `RuntimeDispatcher` 短暂获取当前代，再由 `AgentLoop.process_background_result` 经原角色回报。结果 ID 在执行前保留以防模糊失败后的重复投递；结果回合不能再次捕获用户授权，也不触发新用户回合的副作用。

`process_resources` capability 由 `AppRuntime` 的 `ProcessResourceOwner` 持有，以插件 ID 和版本化 key 复用进程资源。候选代只附加，发布后才切换 active；候选回滚不关闭活资源，停用和应用退出关闭监控并报告清理失败。Herdr 的共享 `TaskService`（`tasks-v2`）与 `AgentWatcher` 不保存旧 runtime、RPC 或任何一代的进程能力：工厂只建空状态，每一代在 setup 里 attach 自己的 `processes`，调用 Herdr 时经 `generations.py` 只取当前已发布那一代的；没有已发布代时，用户发起的任务操作直接报错，监视循环跳过本轮。任务各自保存 Herdr 配置快照；聊天查询只显示当前角色任务，继续使用原 agent/worktree 和新 run ID，取消只有确认停止才成为 cancelled。桌面端 Herdr 页面经 `dashboard.py` 的 `tasks.list` / `tasks.get` 读取全部角色任务，并按 `tasks.changed` 失效事件重读；不提供应用重启恢复。

Herdr 的 `backend/progress.py` 读取当前 task/run 的有界 JSONL 阶段报告，以递增序号去重和拒绝旧报告；`backend/task_management.py` 持有任务读模型（摘要、详情、聊天工具快照）及唯一的「能否继续 / 能否取消 / 是否已结束」判定，与 continue/cancel 的实际拒绝条件一致；`backend/dashboard.py` 在其上提供只读并发的 `tasks.list` / `tasks.get`、继续/取消 RPC 及只含 task ID/revision 的 `tasks.changed` 失效事件，当前代视图订阅随卸载移除。`backend/agents.py` 提供只读并发的 `agents.list` / `agents.get` 与走 integration 通道的 `agents.prompt` / `agents.keys`：用当前代配置的 session 读取全部 agent（按 workspace 分组），按任务自身 session 与 pane ID 关联插件任务；版本/session 检查由 `sessions.py` 的 `SessionGate` 在首次操作前执行，失败时立即重查并优先报告其原因。发 prompt 与按键只经 `backend/agent_control.py` 的 `AgentControl`（面板与角色工具共用，仅记录的来源不同：用户或角色 ID + 名称）：插件任务回合进行中的 agent 拒绝直接输入（以有追踪的取消代替 Ctrl+C），发送期间持有该任务的 `operation_lock` 并在 session 检查之后、发送之前再判断一次，输入校验也只在这里；prompt 等到 agent 开始工作或提问即返回，超时 / stalled 记为未确认、不重发；指令、来源、记录（`AgentCommandLog`）与接手关系（`Handover`，角色 ID 只取自宿主抓取的目标）定义在 `backend/agent_commands.py`，发送与监视两侧共用、互不循环依赖；每个 agent（session + pane ID）的最近 100 条指令记录在 `process_resources` 的 `agent-commands-v2` 中跨配置重载保留、不做重启恢复，由 `agents.get` 返回。角色工具在 `backend/agent_tools.py`：`herdr_list_agents` / `herdr_read_agent`（只读）与 `herdr_prompt_agent` / `herdr_send_keys`（`external-side-effect`，宿主的 risk 只用于工具检索过滤，不触发确认）作用于整个所选 session，复用 `SessionAgents` 的读取与 `AgentControl` 的发送，角色名取自 `roles` 能力，预期失败以 `{ok: false, error}` 返回。写工具在回合内 `background_results.capture()`，`AgentControl` 在指令交给 Herdr 时让该角色成为 agent 的接手角色；`backend/agent_watch.py` 的 `AgentWatcher`（`process_resources` 的 `agent-watches-v2`，工厂只建无能力的空对象，每一代 setup 时 `attach` 自己的 `process_resources` / `processes`，读取时只用 active 的那一代，自建本模块的 `HerdrCli`，不混用其他代的 `CommandError`）保存接手关系，对送达或未确认送达且有回报目标的指令每个 agent 起一个脱离运行时上下文的监视任务：working 后 idle/done、按键前所读 `state_change_seq` 之后的 blocked、agent 消失、指令后长时间未见 working、超过 `task_timeout_seconds` 或连续读取失败时结束，结果确定时即固定本批指令，按目标角色与会话分组各回报一次（ID 取组内最新指令）；回报回合里宿主拒绝 capture，此时写工具只允许 agent 当前的接手角色复用其接手时抓取的目标，面板指令回报给发送时的接手角色，没有则不回报；停用或退出时取消监视，不影响 agent。`ui/index.tsx` 的 nav page 带 `sidebar`：宿主二级栏（`AgentSidebar.tsx`）按 workspace 列出 agent，承载插件任务的 agent 显示为该任务，其余插件任务归入「插件任务」组；主区 `DashboardPage.tsx` 展示选中 agent（`AgentDetailView.tsx`：共用 `AgentHeader.tsx` 头部（其下 `AgentHandlerLine.tsx` 显示接手角色或「无人接手，不会回报」）与 `CommandLog.tsx` 指令记录（含回报状态），底部 `AgentComposer.tsx` 直接发消息并带 `InterruptButton.tsx`（Ctrl+C）；关联任务时其下复用 `TaskDetailView.tsx`，回合进行中只能取消任务，回合结束后底部的追加要求可用，并附加「直接发送」与中断；两种输入共用 `Composer.tsx`）或无 agent 的任务；两个挂载点共享 `dashboardStore.ts`（选中项、任务列表、agent 列表、角色，最新挂载的 client 驱动），读取由 `taskFeed.ts` 完成：任务先订阅后读取、合并失效并拒绝旧修订，agent 在上次读取结束后按间隔轮询、卸载即停，页面卸载不停止任务。看板的全局范围不改变角色工具权限；PR 打开使用通用 `host.openExternal`，复用宿主原有协议校验。

## 修改影响

- 修改 phase 上下文：检查所有插件 handler、记忆生命周期、自动 CG 和观测插件。
- 修改 Tool/ToolMeta：检查 registry、搜索索引、MCP 同步、提示词渲染和调用结果事件。
- 修改执行器：检查 hook 顺序、错误冒泡、后台任务和工具事件日志。
- 修改 MCP 生命周期：检查连接重建、工具卸载、名称冲突和配置持久化。
- 修改上下文压缩：检查模型注册字段、自动与手动压缩入口、工作摘要持久化和记忆整理游标。

## 不变量

- phase 的 `requires`/`produces` 契约在构造 phase 时校验：依赖的模块 slot 不存在时该模块被禁用并告警，循环依赖或 slot 重复直接报错。
- 工具调用异常应进入回合错误路径，不能由业务层静默吞掉。
- 插件卸载或 MCP 断开后，相关工具不能残留在 registry。
