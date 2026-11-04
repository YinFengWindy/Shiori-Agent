---
title: 主动行为与 Drift
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - plugins/proactive/backend/plugin.py
  - plugins/proactive/backend/service.py
  - plugins/proactive/backend/loop.py
  - plugins/proactive/backend/agent_tick_factory.py
  - plugins/proactive/backend/state.py
  - plugins/proactive/backend/turn/
  - plugins/proactive/backend/target_selection.py
  - plugins/proactive/backend/sensor.py
  - plugins/proactive/backend/config_loader.py
  - plugins/proactive/backend/plugin_config.py
  - plugins/proactive/backend/drift.py
  - plugins/proactive/backend/drift_state.py
  - plugins/proactive/backend/drift_tools.py
  - apps/backend/agent/proactive_host/
  - apps/backend/bootstrap/proactive_config_migration.py
  - apps/backend/core/identity/
  - plugins/proactive/ui/roleProactiveDefaults.ts
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
---

# 主动行为与 Drift

## Proactive

`ProactiveLoop` 驱动周期性 tick。传感器、presence、时间、关系和记忆等信息形成 `AgentTickContext`，随后经过裁定、Agent tick 创建、工具执行和投递。`ProactiveStateStore` 保存节流、最近行为和裁定所需状态。tick 开始时从本代 `CONVERSATION.reply_state` 读取心情目录和已存心情时间，抄进 `InitiatedReply`。主动层只发起；`PROACTIVE_HOST.validate_reply` 校验时读 tick 所在那一代的 `CONVERSATION.reply_state`。

准入（目标、忙碌）先运行；核心场景跟进、关系动机随后独立评估，动机只能认领本轮，不能拦下。关系阈值或关系专属冷却未满足只表示该动机未命中，不阻断 alerts/content 或 Drift。外部内容优先；没有外部内容时按场景跟进、关系 fallback、可用 Drift 的顺序选择。完全没有候选时不调用模型。只有实际用于本轮的场景动机才接收完成回写，外部内容送达不会增加场景跟进次数。

未命中原因（如 `cooldown`、`below_threshold`）保留在 gate trace 和 tick_log 的 `gate_name`、`gate_reason`、`gate_metadata`，`gate_exit` 仅记录全局拒绝。循环是插件的进程资源：每个角色一份，只在本代发布后启动或重绑，随 `RoleCreated` / `RoleDeleted` 增减，执行走已发布代的宿主端口。循环至少每 60 秒（`loop.SETTINGS_CHECK_SECONDS`）经 `ROLES.plugin_settings` 重读开关与配置：关闭后在一次检查内停止 tick 与 feed 轮询，关掉 `proactive.db` 与 MCP 会话（经 `PROCESSES.mcp` 创建）；配置改动在下一次检查时生效并重算下次 tick 时间。循环构造时不解析角色设置，设置读不出来只让该角色记日志并按关闭处理。循环任务用全新的 contextvars 上下文启动，不继承触发它的请求租约；异常退出的循环在下一次发布或角色增删时重建，异常留给 `close()` 抛出。场景追问用 `SCENE.request` 登记；场景订阅在发布时启动，旧代接受的工作排空后清理，未发布候选不消费场景事件。

`[plugins.proactive]` 里的 `scene_followup` 与 `relationship` 是独立布尔开关，默认均为 true，角色主动总开关仍独立生效。`load_config` 把旧 `[agent.proactive_strategies]` 里与默认不同的值迁入该表（插件里已有的键不覆盖），然后删掉旧表。顶层 `[proactive]` 没有运行时消费方，启动时整段删除并记日志，不把里面的值抄进插件表。角色 JSON 的 proactive 字段仍由 `load_proactive_config` 解析。桌面设置页不读也不写这两个开关，保存时 `[plugins.proactive]` 随其他插件表由后端原样保留，不会重建 `[agent.proactive_strategies]`。

### 投递目标

接收会话不再由角色手工勾选或从渠道绑定派生，而是每轮从运行时实时计算（`ProactiveTargetResolver.resolve_saved`）：角色的桌面会话，加上经该角色**在线**渠道账号（`RoleStore.accounts`）与已绑定的桌面用户身份（`RoleStore.identities`，`core/identity/`）之间的私聊，按身份绑定顺序、再按账号顺序排列。角色主动推送关闭时不选目标。角色 JSON 的 `proactive.candidates` 仅作为旧数据按原顺序保留，运行时不读取；主动插件 `settings_set` 保存时清空这项已退役的绑定。核心只保存该不透明对象，不解释其字段。

每轮 tick 由 `plugins/proactive/backend/sensor.py` 的 `target_transport()` 经 `target_selection.py` 选出唯一目标，发送阶段只投递这一处，不再换渠道重发。候选和线程上最后一条用户消息读 `PROACTIVE_HOST`（`candidate_chats`、`last_user_message_at`），主动开关读 `ROLES.plugin_settings(role_id, "proactive")`。桌面在场（`user_at_desktop()`，读 `AppRuntime.desktop_presence`）→ 桌面；否则 → 最近有用户消息的非桌面候选；都没有记录 → 第一个非桌面候选；没有非桌面候选 → 桌面。选中私聊时由宿主投递时解析为对应账号插件与 `AccountTarget("private", user_id)`。按角色构建的运行时用 `ProactiveConfig.role_id` 标明所服务的角色。角色配置里的全局投递目标键（`target` / `default_channel` / `default_chat_id` / `default_role_id`）在加载时被拒绝。`config.toml` 的顶层 `[proactive]` 不再解析，启动迁移直接删掉。

主动行为不是绕开会话的单独机器人：成功输出应写入权威角色会话，并复用统一工具、消息推送和渠道投递。生成与评分使用不同提示词边界：生成链路显式使用角色身份，评分器保持中性，并保留完整的 1-5 分标尺与领域判分规则。

### 自然回复批次

角色启用 `natural_chat_enabled` 时，主动 `message_push` 的草稿正文和 Drift 对话复用共享即时聊天提示与 `reply_sequence` 协议。一次 tick 经 `PROACTIVE_HOST.natural_reply_scope` 只开一个回复作用域；`execute_tool` 把每次工具调用记成计划上的工具事实，作用域结束前提交，计划被作废时也提交。`complete(natural_draft=True)` 在宿主里把草稿变成已校验的消息列表（`agent/proactive_host/natural.py`）。投递只有 `deliver`：作用域内经已打开的计划发出本轮草稿，会话与目标必须属于该计划。`TurnOrchestrator` 持有本轮目标与状态；`agent/turns/proactive_sequence.py` 逐条发送、记账并发布真实持久消息 ID。已开始的单次发送有界收尾，未发尾段可取消。投递一旦有消息落库，调用方的取消或计划被打断不会丢掉结果：端口返回已落库的部分，取消在调用方下一次 `await` 时再抛出，调用方据返回值跑成功/失败副作用（`plugins/proactive/backend/turn/delivery.py`）；整条都已落库后抛出的任何异常（presence、好感记账、重新取得角色闸门、最终心情写入、提交事件）都只记日志，期间收到的取消仍会再抛出。部分送达事件只包含确认前缀。普通显式发送工具的原始 payload 不经过这条生成路径。

自然主动改投通过渠道插件的只读 `account.resolve` 获得规范入站地址；默认绑定私聊复用既有目标选择器的地址，后台结果复用原始入站快照，不额外查询渠道。插件仍拥有平台 ID 解析、群准入、点名与发送；宿主只按角色、渠道实例、接收账号、聊天类型、chat/topic 和实际发送者维护批次。无对象群主动批次可被首个已准入去重请求取消，有对象时其他发送者请求保序等待。`ChannelSequenceOwner` 在换代时作废旧计划；每段投递继续检查角色能力和账号连接归属。

## Drift

角色「能力 → 运行能力」的「主动推送」开关统一控制主动消息与空闲活动。空闲活动的最大步数、最小间隔位于「运行能力」下方「主动推送」分区（同区还有推送策略 profile）的「执行参数」折叠项中。配置加载时 `drift_enabled` 由主开关派生；旧数据中的 `drift.enabled` 仍可读取，但不再覆盖主开关，角色编辑保存时移除该旧字段。

Drift 是独立于普通被动消息的特殊回合模式。`DriftStateStore` 保存状态，`DriftTurnPipeline` 负责执行，`plugins/proactive/backend/drift_tools.py` 提供相关工具接入。它与 Proactive 共享触发和投递基础设施，但拥有自己的回合语义与状态迁移。Drift 必须显式取得当前角色 prompt，并完整读取该角色的 `SELF.md`、长期记忆与最近上下文；任一读取失败都终止本轮，不能退化为无记忆的通用回复。内置 skill 的 `state.json` 写在角色自己的 drift skills 目录，`SKILL.md` 仍留在安装树；`read_file("skills/<name>/...")` 先读 drift 目录里的那份，没有才读内置目录。Drift 的文件工具走 `PROACTIVE_HOST.run_drift_file_tool`：只能在 `execute_tool` 的 invoker 里调用，写入与编辑由宿主限制在 `roles/<role_id>/drift`。

## 数据位置

配置与频率诊断日志在 `plugin-data/proactive/logs/`，文件名为 `proactive_config_trace.jsonl`、`proactive_rate_trace.jsonl`。冷启动迁入旧 `memory/` 下的同名文件，已有新目标优先，旧文件核对后归档；见[存储决策](../../decisions/2026-11-04-plugin-storage-paths.md)。`proactive_sources.json` 仍在工作区根，MCP 登记从 `plugin-data/mcp/mcp_servers.json` 读取。角色状态库 `roles/<id>/proactive.db` 和该角色的 Drift 目录继续随角色保留与删除。

## 修改影响

- 修改 tick 频率或门控：检查 presence、寂寞、关系维护、调度任务和重复投递。
- 修改门控诊断：检查 `ProactiveGateDecision`、gate trace、`tick_log` schema 迁移和桌面状态展示。
- 修改裁定上下文：检查 AgentTickFactory、日志、状态持久化和提示词 token 预算。
- 修改主动消息：检查 Session/Conversation 同步与目标选择（`target_selection.py`，目标选择只在主动循环里用），以及账号在线状态与用户身份绑定对候选集合的影响。
- 修改 Drift 状态：检查状态迁移、工具可见性、恢复逻辑和普通回合互斥。

自然聊天开启时，内部主动 `message_push` 草稿的正文改为 `messages` 列表，沿用被动回复的 `NaturalReplyProtocol` 校验与最多一次 completion-only `finish_reply` 纠正；证据、目标与 `finish_turn` / `finish_drift` 控制保留。显式发送工具不接入这条生成协议。主动路径直接投递已校验消息数组；没有被动正文装饰器，不把临时分隔标记写入日志或去重键。账号请求截止时间由各渠道原生 transport 拥有。

## 不变量

- 无状态变化时 store 更新应返回旧状态，避免循环触发。
- 主动投递必须有稳定的角色、会话和目标渠道。
- 一条主动消息只提交一次权威角色会话、只投递到一个目标，并发出一次 `InitiatedMessageCommitted`（`source="proactive"`）；没有跨渠道重发。
- 同一 tick 的裁定、工具步骤和最终结果应可追踪。

主动说明由 `plugins/proactive/backend/role_prompt.py` 通过 `PromptRendering` 提供，使用当前角色的 `roles/<id>/PROACTIVE_CONTEXT.md`。核心 prompt 不再持有主动业务段。宿主 presence 只从 `SessionManager.presence` 获取；插件经 `SESSIONS.presence` 读取。场景观察的发布时机继续由 `SCENE_HOST.on_published` 保持，不能直接替换为更早的进程资源发布通知，见[评估](../../decisions/2026-11-02-p6b-publication-and-cleanup.md)。
