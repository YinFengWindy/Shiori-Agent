# 插件变更

SDK 源版本是 `packages/sdk/python/shiori_sdk/_version.py`。大版本是破坏性变更。这里只记已经定版的变更，不设 Unreleased 批次。

## 4.0.0

尚未发布到 npm / PyPI。桌面要等插件系统重构做完才带这个 SDK 出包。

- manifest 只接受 `api: 4`，并要求 `sdk` 最低约束。基线是 `>=4.0.0`。
- 删除 `runtime_api`。SDK 版本就是唯一版本号。
- `SESSIONS.presence`、`ROLES.plugin_settings`、`CONVERSATION.deliver_initiated_reply` 和 `InitiatedMessageCommitted` 进入 4.0 基线。`ROLES.plugin_settings` 写入 `proactive` 时清空已退役的 `candidates`，与桌面保存角色一致。
- `SESSIONS.presence` 新增 `most_recent_user_at()`：所有会话里用户最近一次发言的时间（#907 P6b-1a，主动循环的传感器用它）。宿主旧的 `proactive_v2` 心跳存储删除，核心与主动循环都改用 `SESSIONS.presence`，存储列不变。
- **发版门闩**：`CONVERSATION` 现在没有提供方。带 SDK 4.0 的桌面版本发出之前，宿主必须提供 `CONVERSATION`（`deliver_initiated_reply` 与 `InitiatedMessageCommitted`）。
- 同一次大版本内，已有 Key 不再加方法。新能力用新 Key 或新 Event。
- 运行时契约长文改为本目录的[指南](plugin-guide.md)、[生命周期与准入](plugin-lifecycle.md)、[前端契约](plugin-frontend.md)和生成的 [API 参考](plugin-api.md)。
- `shiori_sdk.testing.bridge` 移到 `shiori_host_testing.bridge`。
- P6a 新增 Key（`shiori_sdk.core`）。插件提供、核心消费：`REPLY_POLICY`（natural_chat）、`SCENE`（scene）、`AFFECTION`（affection）。宿主提供：`SCENE_HOST`、`AFFECTION_HOST`、`MCP_TOOLS`。`SCENE_HOST.on_published` 让场景插件在本代发布时开始观察，代内重载或启用时立即开始。
- `ProactiveMessageCommitted` 进入 SDK（`shiori_sdk.role_events`），插件订阅与宿主发布用同一个类型。
- 前端新增 UI 槽 `roleAffection`（角色页好感 tab）与 `chatAffection`（聊天状态栏里的好感区块：关系标签、好感条、寂寞值）。两个槽都注入 `client` 与 `host`；props 只给定位用的标识：`roleAffection` 是 `{roleId, bridgeReady}`，`chatAffection` 是 `{roleId}`（`PluginChatAffectionComponentProps`）。插件经自己的 RPC 取数（好感插件是 `history`、`chat_status`、`stage_prompts_get/set`），按 `host.onEvent` 收到的 `session.updated`（`payload.role_id`）刷新；宿主不读、不转发插件数据。
- **breaking**（前端）：`RoleRecord` 与会话 metadata 不再带 `relationship_snapshot`、`loneliness_runtime`、`affection`；SDK 删除 `RelationshipSnapshot`、`LonelinessRuntime`、`RelationState` 类型。`AffectionSummary` 保留，由好感插件的 RPC 返回。桥接与会话不再把这些数据写进会话 metadata；会话库打开时一次性删掉已存会话 metadata 里的这三个键（见[生命周期](plugin-lifecycle.md#启动时的配置迁移)）。
- 好感插件在每次寂寞心跳（同时结算衰减）和关系快照刷新后发 `plugin.affection.chat_status.changed`（`{role_id}`），聊天侧栏据此重新读取。
- `AFFECTION` 只保留核心实际调用的方法（提示、记账、场景与主动策略、记忆整理后的快照刷新、初始化）；`AFFECTION_HOST` 删除 `save_session`，`AffectionSession.metadata` 只读。
- **breaking**：删除 `SCENE_OBSERVATIONS`（`scene_observations`）、`shiori_sdk.roles.SceneObservations` 与 testing 里的 `FakeSceneObservations` / `fake_scene_observations`。改用可选注入 `scene`，`get(SCENE)` 为 `None` 时不登记需求。
- 系统插件 `natural_chat`、`affection`、`scene` 默认启用。外部插件 `mcp` 新装默认关闭；`mcp_servers.json` 里已有服务器、且 `[plugins.mcp]` 未显式写 `enabled` 的工作区，启动时一次性写入 `enabled = true`（见[生命周期](plugin-lifecycle.md#启动时的配置迁移)）。`[agent.scene_observation]` 一次性迁到 `[plugins.scene]`。
- 新增宿主 Key `SCHEDULE_HOST`（`shiori_sdk.core.schedule_host`，#906 P6s-1）：`deliver` 以角色身份把消息投到计划任务的目标，`run_turn` 跑一次计划任务回合并返回回复（不投递）；两者都走当前发布代，端口本身跨代。入参 `ScheduledRun` 是一次到期执行（任务 ID 与名义触发时间决定投递去重键）。同模块导出 `scheduler_thread_id`，宿主识别计划任务线程用同一格式。
- 新增 Key `SCHEDULER`（`shiori_sdk.core.scheduler`，#906 P6s-2），由系统插件 `schedule` 提供：`create_job(ScheduleRequest)`、`list_jobs(role_id)`、`cancel_job(role_id, job_id)`，返回 `ScheduledJobInfo`。消费方 `optional_inject: [scheduler]`。调度器搬进插件，作为插件的进程资源跨代只有一份；`schedules.json` 的路径与格式不变。核心不再注册 `schedule` / `list_schedules` / `cancel_schedule`，`[agent.wiring] toolsets` 里的 `"schedule"` 保留为不注册任何东西的名字，默认值去掉它。
- **breaking**（桌面桥接）：删除 `roles.tasks.create` / `roles.tasks.update`；`roles.tasks.list` / `cancel` 只返回后台任务与记忆维护，任务对象不再有 `next_run_at`、`editable`、`schedule`。计划任务改走插件 RPC `plugin.schedule.{list,create,update,cancel}`（`list`、`cancel` 在重载暂停准入时仍可用），变化后插件发 `plugin.schedule.tasks.changed`（`{role_id}`）。
- 前端新增 UI 槽 `roleTasks`（聊天右栏「任务」面板里的计划任务区块，`PluginRoleTasksComponentProps`）：props 是 `{roleId, view, onViewChange}`，`view` 为空时区块作为任务列表的一组，否则区块自己定义的视图占满面板，宿主只保存这个值、换角色时清空。SDK 新增导出（renderer peer ABI）：`chatSidebarPanelClass`、`chatSidebarHeaderClass`、`chatSidebarScrollableClass` 与 `DetailRow`（宿主原有，移进 SDK 共用；面板改用新语义 token `--color-bg-glass-soft` / `--color-border-glass`，即 `bg-surface-glass-soft` / `border-line-glass`），以及任务面板的组头与行 `roleTaskGroupHeadClass`、`roleTaskGroupCountClass`、`roleTaskRowClass`、`roleTaskRowTitleClass`、`roleTaskRowSummaryClass`（宿主后台/记忆组与插件计划任务组共用）。
- 新增宿主 Key `MARKDOWN_MEMORY`（`shiori_sdk.core.markdown_memory`，#907 P6b-3）：`role(role_id)` 返回 `RoleMarkdownMemory`（角色不存在时 `None`），有 `read_long_term`、`read_self`、`write_self`、`self_seed_pending`、`snapshot_pending`、`commit_long_term(content, *, history_entry)`、`rollback_pending_snapshot`、`read_state`、`write_state(key, value)`；`default_self` 是 SELF.md 模板。端口本身跨代，文档路径与格式不变。
- 新增 Key `MEMORY_OPTIMIZER`（`shiori_sdk.core.memory_optimizer`，#907 P6b-3），由新系统插件 `memory_optimizer`（0.1.0，默认启用）提供：`active_run()` 返回 `MemoryOptimizationRun`（`role_id`、`started_at`）或 `None`。后台记忆整理从核心搬进该插件，整理循环是插件的进程资源，跨代只有一份；开关只看插件启停，间隔改为 `[plugins.memory_optimizer].interval_seconds`。
- **breaking**（配置）：删除 `Config.memory_optimizer_enabled` / `memory_optimizer_interval_seconds` 与 `[agent.maintenance]` 段。启动时 `[agent.maintenance]`（及顶层同名回退键）一次性迁到 `[plugins.memory_optimizer]`：`memory_optimizer_enabled = false` 变成 `enabled = false`，间隔变成 `interval_seconds`（不小于 60），与默认值相同的不写，插件表已有的键不覆盖，迁完删除旧键（见[生命周期](plugin-lifecycle.md#启动时的配置迁移)）。桌面设置页「高级」不再有后台整理记忆的开关与间隔，保存设置也不再写 `[agent.maintenance]`。
- 代内启用或停用插件时，正在运行、用 `optional_inject` / `optional_dependencies` 依赖它的插件（及其硬依赖方）先排空，再随切换重新 setup，`was_active` / `is_reload` 为 `True`，不再保留切换前读到的可选依赖（#949，见[生命周期](plugin-lifecycle.md#启用与停用)）。
