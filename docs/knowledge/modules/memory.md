---
title: 记忆系统
kind: 领域说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - core/memory/
  - plugins/default_memory/
  - memory2/
  - agent/retrieval/
related:
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# 记忆系统

## 分层

- `core/memory/` 定义 `MemoryEngine`、查询、变更和运行时契约，并提供生命周期接入点。
- `plugins/default_memory/` 是默认记忆插件与 engine 策略实现，负责查询、变更、管理和提示词。
- `memory2/` 提供增强处理链，包括查询构造/改写、HyDE、召回、充分性判断、去重、注入规划、画像与响应后记忆化。
- `agent/retrieval/` 将具体记忆召回适配到 Agent 上下文准备阶段。

## 典型数据流

回合前根据角色、会话和当前输入构建 `MemoryQuery`，召回结果经过过滤、重排或注入规划进入上下文。回合后由后台 worker 判断是否写入、合并或 supersede 旧记忆。显式的 `memorize`、`forget_memory`、`recall_memory` 工具复用同一记忆契约。

## 修改影响

- 修改记忆记录 schema：检查 store、向量索引、时间索引、迁移、去重和管理工具。
- 修改召回评分：检查注入阈值、HyDE 合并、上下文 token 预算和评测；不要无意重写原始 score。
- 修改角色/群聊隔离：检查查询过滤、权限策略、会话键和响应后写入。
- 修改生命周期接入：检查 `BeforeTurn` 上下文准备和响应后的异步整理，不要阻塞消息投递。

## 不变量

- 角色和会话的记忆域必须显式过滤，不能依赖提示词约束实现隔离。
- 召回结果与持久化记录分离；派生分数不应破坏原始证据。
- 后台整理失败必须留下可查询的明确原因。
