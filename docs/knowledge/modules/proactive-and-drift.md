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
  - apps/backend/agent/core/proactive_turn/delivery.py
  - apps/backend/proactive_v2/target_selection.py
  - apps/backend/agent/core/proactive_turn/strategies.py
  - apps/backend/agent/core/proactive_turn/scene_subscription.py
  - apps/backend/agent/proactive_preferences.py
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

全局准入（目标、忙碌和扩展 gate）先运行；核心场景跟进、关系动机随后独立评估。关系阈值或关系专属冷却未满足只表示该动机未命中，不阻断 alerts/content 或 Drift。外部内容优先；没有外部内容时按场景跟进、关系 fallback、可用 Drift 的顺序选择。完全没有候选时不调用模型。只有实际用于本轮的场景动机才接收完成回写，外部内容送达不会增加场景跟进次数。

未命中原因（如 `cooldown`、`below_threshold`）保留在 gate trace 和 tick_log 的 `gate_name`、`gate_reason`、`gate_metadata`，`gate_exit` 仅记录全局拒绝。核心策略随 runtime generation 装配；场景订阅在发布时启动，旧代接受的工作排空后清理，未发布候选不消费场景事件。

`[agent.proactive_strategies]` 中的 `scene_followup` 与 `relationship` 是独立布尔开关，默认均为 true，角色主动总开关仍独立生效。配置加载将旧 `[plugins.relationship_proactive].enabled = false` 或两个旧代码位置的 `plugin.disabled` 一次性迁为缺失的核心开关；已有核心键优先。旧标记和配置可保留作历史数据，不再参与插件发现，核心键齐全后不再读取旧停用偏好。候选配置验证不做文件 IO。

### 投递目标

角色的主动推送配置保存一组接收会话（`RoleProactiveConfig.candidates`，引用角色自己的绑定，顺序即绑定顺序）。新增私聊与桌面绑定默认进入候选、群聊默认不进入，这一默认只在渲染端 `roleProactiveCandidates.ts` 决定；后端只校验候选必须是已绑定会话、启用时至少一个候选，删除绑定时同步移除候选（候选清空则关闭主动推送）。清单 v9 迁移把旧的单一目标与桌面绑定转为候选。

每轮 tick 在 gate 阶段由 `proactive_v2/target_selection.py` 选出唯一目标，发送阶段只投递这一处，不再换渠道重发：桌面为候选且桌面在场（`AppRuntime.desktop_presence`，由 `build_proactive_runtime` 显式传入）→ 桌面；否则 → 最近有用户消息的非桌面候选（读 `messages` 表中该候选线程 `thread:<role>:<channel>:<chat_id>` 的最后一条用户消息）；都没有记录 → 第一个非桌面候选；没有非桌面候选 → 桌面。候选每轮从角色清单实时读取。桌面端「当前」标记通过 `roles.proactive.target` 调用同一 resolver，渲染端不重复实现规则。`config.toml` 不再有全局投递目标：`[proactive.target]` 与 `[proactive]` 根级 `default_channel` / `default_chat_id` / `default_role_id` 在启动时由 `agent/proactive_target_migration.py` 一次性删除，之后再出现会被配置加载拒绝；按角色构建的运行时用 `ProactiveConfig.role_id` 标明所服务的角色。

主动行为不是绕开会话的单独机器人：成功输出应写入权威角色会话，并复用统一工具、消息推送和渠道投递。生成与评分使用不同提示词边界：生成链路显式使用角色身份，评分器保持中性，并保留完整的 1-5 分标尺与领域判分规则。

## Drift

Drift 是独立于普通被动消息的特殊回合模式。`DriftStateStore` 保存状态，`DriftTurnPipeline` 负责执行，`apps/backend/proactive_v2/drift_tools.py` 提供相关工具接入。它与 Proactive 共享触发和投递基础设施，但拥有自己的回合语义与状态迁移。Drift 必须显式取得当前角色 prompt，并完整读取该角色的 `SELF.md`、长期记忆与最近上下文；任一读取失败都终止本轮，不能退化为无记忆的通用回复。

## 修改影响

- 修改 tick 频率或门控：检查 presence、寂寞、关系维护、调度任务和重复投递。
- 修改门控诊断：检查 `ProactiveGateDecision`、gate trace、`tick_log` schema 迁移和桌面状态展示。
- 修改裁定上下文：检查 AgentTickFactory、日志、状态持久化和提示词 token 预算。
- 修改主动消息：检查 Session/Conversation 同步与目标选择（`target_selection.py`，桌面端预览共用）。
- 修改 Drift 状态：检查状态迁移、工具可见性、恢复逻辑和普通回合互斥。

## 不变量

- 无状态变化时 store 更新应返回旧状态，避免循环触发。
- 主动投递必须有稳定的角色、会话和目标渠道。
- 一条主动消息只提交一次权威角色会话、只投递到一个目标，并发出一次 `ProactiveMessageCommitted`；没有跨渠道重发。
- 同一 tick 的裁定、工具步骤和最终结果应可追踪。
