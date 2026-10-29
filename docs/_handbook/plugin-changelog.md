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
