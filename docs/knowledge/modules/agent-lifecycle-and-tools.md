---
title: Agent 生命周期、工具、插件与 MCP
kind: 领域说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - agent/core/
  - agent/turns/
  - agent/lifecycle/
  - agent/tools/
  - agent/plugins/
  - agent/mcp/
related:
  - memory.md
  - proactive-and-drift.md
  - architecture/overview.md
---

# Agent 生命周期、工具、插件与 MCP

## 回合生命周期

被动回合由 `agent/core/passive_turn/` 组织，`agent/turns/` 负责回合协调和输出。生命周期模块提供 `BeforeTurn`、`BeforeReasoning`、`AfterReasoning`、`AfterTurn`、prompt render 等 phase，使记忆、插件、自动 CG 和观测逻辑在明确边界接入。

## 工具体系

`ToolRegistry` 保存工具和索引视图，搜索后端支持按需发现工具。ToolExecutor 执行调用，ToolHook 在执行前后接入插件逻辑。文件、Shell、消息、记忆、调度、图片、网页和 subagent 等能力都是具体工具实现。

工具搜索的目的是控制可见工具规模；搜索结果进入当前回合，不应永久污染全局 registry。后台 Shell 任务由独立 runtime 管理注册、轮询和停止。

## 插件与 MCP

`agent/plugins/` 管理插件注册、配置、生命周期和装饰器。`agent/mcp/registry.py` 与 `client.py` 管理 MCP server 配置和连接池，并把远端工具同步到 ToolRegistry。插件工具 hook 会适配到统一 ToolExecutor 接口。

## 修改影响

- 修改 phase 上下文：检查所有插件 handler、记忆生命周期、自动 CG 和观测插件。
- 修改 Tool/ToolMeta：检查 registry、搜索索引、MCP 同步、提示词渲染和调用结果事件。
- 修改执行器：检查 hook 顺序、错误冒泡、后台任务和工具事件日志。
- 修改 MCP 生命周期：检查连接重建、工具卸载、名称冲突和配置持久化。

## 不变量

- phase 的 `requires`/`produces` 契约在启动时校验。
- 工具调用异常应进入回合错误路径，不能由业务层静默吞掉。
- 插件卸载或 MCP 断开后，相关工具不能残留在 registry。
