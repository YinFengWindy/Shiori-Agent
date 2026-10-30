# 插件变更

SDK 源版本是 `packages/sdk/python/shiori_sdk/_version.py`。大版本是破坏性变更。这里只记已经定版的变更，不设 Unreleased 批次。

## 4.0.0

尚未发布到 npm / PyPI。桌面要等插件系统重构做完才带这个 SDK 出包。

- manifest 只接受 `api: 4`，并要求 `sdk` 最低约束。基线是 `>=4.0.0`。
- 删除 `runtime_api`。SDK 版本就是唯一版本号。
- `SESSIONS.presence`、`ROLES.plugin_settings`、`CONVERSATION.deliver_initiated_reply` 和 `InitiatedMessageCommitted` 进入 4.0 基线。`ROLES.plugin_settings` 写入 `proactive` 时清空已退役的 `candidates`，与桌面保存角色一致。
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
- 代内启用或停用插件时，正在运行、用 `optional_inject` / `optional_dependencies` 依赖它的插件（及其硬依赖方）先排空，再随切换重新 setup，`was_active` / `is_reload` 为 `True`，不再保留切换前读到的可选依赖（#949，见[生命周期](plugin-lifecycle.md#启用与停用)）。
