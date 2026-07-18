---
title: 主动行为与 Drift
kind: 领域说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - proactive_v2/loop.py
  - proactive_v2/agent_tick_factory.py
  - proactive_v2/state.py
  - proactive_v2/drift_state.py
  - agent/core/drift_turn.py
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
---

# 主动行为与 Drift

## Proactive

`ProactiveLoop` 驱动周期性 tick。传感器、presence、时间、关系和记忆等信息形成 `AgentTickContext`，随后经过裁定、Agent tick 创建、工具执行和投递。`ProactiveStateStore` 保存节流、最近行为和裁定所需状态。

主动行为不是绕开会话的单独机器人：成功输出应写入权威角色会话，并复用统一工具、消息推送和渠道投递。

## Drift

Drift 是独立于普通被动消息的特殊回合模式。`DriftStateStore` 保存状态，`DriftTurnPipeline` 负责执行，`proactive_v2/drift_tools.py` 提供相关工具接入。它与 Proactive 共享触发和投递基础设施，但拥有自己的回合语义与状态迁移。

## 修改影响

- 修改 tick 频率或门控：检查 presence、寂寞、关系维护、调度任务和重复投递。
- 修改裁定上下文：检查 AgentTickFactory、日志、状态持久化和提示词 token 预算。
- 修改主动消息：检查 Session/Conversation 同步、目标渠道解析和失败重试。
- 修改 Drift 状态：检查状态迁移、工具可见性、恢复逻辑和普通回合互斥。

## 不变量

- 无状态变化时 store 更新应返回旧状态，避免循环触发。
- 主动投递必须有稳定的角色、会话和目标渠道。
- 同一 tick 的裁定、工具步骤和最终结果应可追踪。
