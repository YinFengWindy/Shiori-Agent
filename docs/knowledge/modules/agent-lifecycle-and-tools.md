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
  - apps/backend/agent/tool_hooks/
  - apps/backend/agent/plugin_host/
  - apps/backend/agent/mcp/
  - apps/backend/core/compaction.py
  - plugins/screen_perception/backend/
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

`ToolRegistry`（`agent/tools/registry.py`）保存工具和索引视图，`search_backend.py` 的关键词后端配合 `tool_search` 工具支持按需发现工具。`agent/tool_hooks/` 的 `ToolExecutor` 执行调用，`ToolHook` 在执行前后接入插件逻辑。文件、Shell、消息推送与历史查询、记忆、调度、网页抓取与搜索、subagent（`spawn`）、群环境与群旁听、成员查询、账号投递（`account_*`）、MCP 管理等能力都是 `agent/tools/` 下的具体工具实现；图片生成等能力由插件注册（如 `plugins/novelai/`）。

工具搜索的目的是控制可见工具规模；初始可见集合由 always-on 工具加会话历史中已发现的工具组成（`passive_turn/tool_visibility.py`），搜索结果进入当前回合，不应永久污染全局 registry。外部上下文（群聊、陌生私聊）中非已绑定用户触发的受限回合只能使用注册时声明 `external_allowed` 的工具，可附带参数取值限制，规则在 `agent/tools/external_access.py` 与 `ToolRegistry.external_denial`。后台 Shell 任务由 `agent/tools/shell/background.py` 管理注册、轮询和停止。

`observe_screen` 由独立的「24h视奸插件」（`plugins/screen_perception/`）注册，启用时桌面、Telegram、QQ 等渠道的当前角色均可使用。插件按需捕获主屏并调用角色配置的视觉模型，只向角色返回经过过滤的活动摘要，不执行桌面动作。停用时撤销工具并取消活动分析；不依赖桌宠或 `observe` 遥测插件。持续感知扩展由 #292 承接。

## 插件与 MCP

插件包位于顶层 `plugins/<id>/`（`manifest.yaml` + `backend/`、`ui/` 等子目录），对外 API 由 `packages/sdk/python/shiori_sdk/` 提供。宿主侧 `apps/backend/agent/plugin_host/` 的 `PluginKernel` 负责插件发现与准入、manifest 解析、依赖加载、setup 装配、失败回滚和卸载；能力（工具、渠道、账号、后台任务、bot 命令等）经 capabilities 与作用域服务暴露给插件。插件的 pre-tool handler 由 `plugin_host/tool_hooks.py` 的 `PluginToolHook` 适配到统一 ToolExecutor 接口。`apps/backend/agent/mcp/registry.py`（`McpServerRegistry`，持久化到 `mcp_servers.json`）与 `client.py` 管理 MCP server 配置和 stdio 连接，并把远端工具同步到 ToolRegistry；`manage_tools.py` 提供 `mcp_add` / `mcp_remove` / `mcp_list` 工具。

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
