---
title: 渠道系统
kind: 领域说明
status: 当前有效
last_verified_commit: 65df50ba
source_paths:
  - apps/backend/infra/channels/
  - apps/backend/core/channels/hub.py
  - plugins/qqbot/
  - plugins/feishu/
  - plugins/telegram/
  - plugins/qq/
  - apps/backend/bootstrap/channels.py
  - apps/backend/bootstrap/channel_host.py
  - apps/backend/agent/channel_config_migration.py
  - apps/backend/desktop_bridge/runtime/channel_listing.py
related:
  - conversations-and-sessions.md
  - desktop-and-bridge.md
---

# 渠道系统

## 统一边界

外部渠道全部由插件提供，宿主只拥有 `desktop`，不再有内置渠道或「频道」设置分区（#363）。`apps/backend/infra/channels/contract.py` 定义 Channel 合约、可选钩子与 `ChannelContext`；插件在 manifest 静态声明渠道，`setup` 里经 `ctx.channels.add()` 贡献实例。`apps/backend/bootstrap/channels.py` 的 `start_channels` 只装配插件贡献的渠道：构造共享上下文，按 `configuration_key`（声明 `uses_bot_commands` 的渠道再加上 bot 命令列表）跨代复用未变的连接；`bootstrap/channel_host.py` 负责启停、换代时的入站暂停与回滚、已移除连接的排空。`apps/backend/core/channels/hub.py` 做绑定校验与入站路由，`core/common/channel_directory.py` 按渠道名向已发布的连接查询钩子。`desktop_bridge/runtime/channel_listing.py` 的 `channels.list` 把 `desktop` 与各插件的静态声明合并上运行状态，供角色绑定面板使用。渠道配置在各自的 `[plugins.<id>]`，由「设置 › 插件」的自动表单编辑。

| 插件 | 渠道名 | 结构 |
| --- | --- | --- |
| `plugins/telegram/` | `telegram` | `backend/channel/` 拆分 lifecycle、inbound、outbound、media、streaming、commands；`backend/utils/` 负责限流、渲染与 live 编辑；声明 `uses_bot_commands` |
| `plugins/qq/`（QQ（NapCat）） | `qq` | lifecycle 只装配 NcatBot 与订阅，inbound、outbound、trace、loop bridge、群聊过滤各自独立；ws_uri/ws_token 每次激活显式写入 NcatBot 进程级配置（留空恢复 SDK 原值）；运行目录 `~/.shiori/ncatbot` |
| `plugins/qqbot/` | `qqbot` | `channel.py` 只做组合与启停，Gateway、C2C 入站、HTTP/媒体出站、live stream 分属各 mixin |
| `plugins/feishu/` | `feishu` | lark-oapi 长连接跑在独立线程和私有事件循环（`ws.py`），回调只去重并交回宿主循环；REST 在 `api.py`，入站解析在 `inbound.py`，CardKit 流式卡片在 `streaming.py` |

QQ 群会话的规范 chat_id 是 `gqq:<群号>`，裸号一律是私聊，核心 `core/common/channel_identifiers.py` 严格比较、不再把裸号视同群；旧角色清单里的裸群号由 `core/roles/migration.py`（v6）一次性改写为 `gqq:`。旧版的 `[channels.telegram]` / `[channels.qq]` 由 `agent/channel_config_migration.py` 在启动时一次性迁到 `[plugins.telegram]` / `[plugins.qq]`，该迁移长期保留；迁移后仍出现的非空旧表直接报错。新增渠道的写法见 `docs/_handbook/channel-plugins.md`。

## 标识与投递

`session_key.py`、`reply_context.py` 和公共 channel identifier helper 负责稳定定位账号、聊天、线程与回复上下文。群聊过滤和成员隔离必须在入站边界明确处理。typing、流式编辑等辅助动作允许独立失败，但最终消息投递和权威会话写入必须可观测。

外部渠道的角色绑定属于一对一关系：每个渠道会话必须且只能配置一个联系人 ID。入站路由只接受该 ID，或与其匹配的渠道别名；缺失或包含多个联系人的旧配置一律拒绝，避免扩大既有角色可响应的范围。桌面端绑定是应用内会话，不配置外部联系人。

## 修改影响

- 修改 Channel 合约或钩子：检查全部渠道插件、`start_channels`/ChannelHost、`channel_directory`、消息总线、测试替身，以及 `docs/_handbook/plugin-runtime-contract.md` 的 Runtime API 版本。
- 修改聊天标识：检查角色绑定、Session/Conversation 键、群聊记忆域和推送目标。
- 修改角色渠道绑定：检查配置校验、入站身份验证、旧配置迁移和角色编辑界面的联系人字段。
- 修改附件模型：检查 Telegram 媒体、QQ 适配、桌面桥接、自动 CG 和历史消息展示。
- 修改 QQ 渠道：NcatBot 需同步检查主 loop/bot loop 桥接、群聊过滤和 CQ 媒体；QQBot 需同步检查 Gateway intent、token/REST、C2C message id 和 live stream 状态。
- 新增渠道：写成渠道插件（manifest 声明 + 配置模型 + Channel 合约），复用 `ChannelIntake`、会话键解析和输出端口，不复制 Agent 回合逻辑；步骤见 `docs/_handbook/channel-plugins.md`。
- 修改旧渠道配置迁移：它服务于跨版本升级，只能收紧不能删除，检查 `tests/backend/agent/test_channel_config_migration.py`。
