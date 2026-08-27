---
title: 主动行为与 Drift
kind: 领域说明
status: 当前有效
last_verified_commit: 7f427a71
source_paths:
  - apps/backend/proactive_v2/loop.py
  - apps/backend/proactive_v2/agent_tick_factory.py
  - apps/backend/proactive_v2/state.py
  - apps/backend/agent/core/proactive_turn/gates.py
  - apps/backend/agent/core/proactive_turn/phases.py
  - apps/backend/agent/core/proactive_turn/tick_logging.py
  - apps/backend/plugins/relationship_proactive/plugin.py
  - apps/backend/proactive_v2/drift_state.py
  - apps/backend/agent/core/drift_turn.py
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
---

# 主动行为与 Drift

## Proactive

`ProactiveLoop` 驱动周期性 tick。传感器、presence、时间、关系和记忆等信息形成 `AgentTickContext`，随后经过裁定、Agent tick 创建、工具执行和投递。`ProactiveStateStore` 保存节流、最近行为和裁定所需状态。

关系门控的 `gate_exit` 保持兼容的门控类别；具体阻断原因（例如 `cooldown`、`below_threshold`）和判断 metadata 通过 gate trace 写入 `tick_log` 的 `gate_name`、`gate_reason` 与 `gate_metadata` 字段。已有数据库会在启动时补齐这些字段，因此冷却、阈值和关系条件不会再被统一的 `loneliness` 标签遮蔽。

主动行为不是绕开会话的单独机器人：成功输出应写入权威角色会话，并复用统一工具、消息推送和渠道投递。生成与评分使用不同提示词边界：生成链路显式使用角色身份，评分器保持中性，并保留完整的 1-5 分标尺与领域判分规则。

## Drift

Drift 是独立于普通被动消息的特殊回合模式。`DriftStateStore` 保存状态，`DriftTurnPipeline` 负责执行，`apps/backend/proactive_v2/drift_tools.py` 提供相关工具接入。它与 Proactive 共享触发和投递基础设施，但拥有自己的回合语义与状态迁移。Drift 必须显式取得当前角色 prompt，并完整读取该角色的 `SELF.md`、长期记忆与最近上下文；任一读取失败都终止本轮，不能退化为无记忆的通用回复。

## 修改影响

- 修改 tick 频率或门控：检查 presence、寂寞、关系维护、调度任务和重复投递。
- 修改门控诊断：检查 `ProactiveGateDecision`、gate trace、`tick_log` schema 迁移和桌面状态展示。
- 修改裁定上下文：检查 AgentTickFactory、日志、状态持久化和提示词 token 预算。
- 修改主动消息：检查 Session/Conversation 同步、目标渠道解析和失败重试。
- 修改 Drift 状态：检查状态迁移、工具可见性、恢复逻辑和普通回合互斥。

## 不变量

- 无状态变化时 store 更新应返回旧状态，避免循环触发。
- 主动投递必须有稳定的角色、会话和目标渠道。
- 一条主动消息只提交一次权威角色会话并发出一次 `ProactiveMessageCommitted`；后续跨渠道重试只执行 transport dispatch。
- 同一 tick 的裁定、工具步骤和最终结果应可追踪。
