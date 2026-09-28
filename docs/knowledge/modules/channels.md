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
  - apps/backend/desktop_bridge/runtime/channel_listing.py
related:
  - conversations-and-sessions.md
  - desktop-and-bridge.md
---

# 渠道系统

## 统一边界

外部渠道全部由插件提供，宿主只拥有 `desktop`，不再有内置渠道或「频道」设置分区（#363）。`apps/backend/infra/channels/contract.py` 定义 Channel 合约、可选钩子与 `ChannelContext`；插件在 manifest 静态声明渠道，`setup` 里经 `ctx.channels.add()` 贡献实例。`apps/backend/bootstrap/channels.py` 的 `start_channels` 只装配插件贡献的渠道：构造共享上下文，按 `configuration_key`（声明 `uses_bot_commands` 的渠道再加上 bot 命令列表）跨代复用未变的连接；`bootstrap/channel_host.py` 负责启停、换代时的入站暂停与回滚、已移除连接的排空。`apps/backend/core/channels/hub.py` 做账号准入与入站路由，`core/common/channel_directory.py` 按渠道名向已发布的连接查询钩子。`desktop_bridge/runtime/channel_listing.py` 的 `channels.list` 把 `desktop` 与各插件的静态声明合并上运行状态，供角色绑定面板使用。渠道配置在各自的 `[plugins.<id>]`，由「设置 › 插件」的自动表单编辑。

| 插件 | 渠道名 | 结构 |
| --- | --- | --- |
| `plugins/telegram/` | `telegram` | `backend/channel/` 拆分 lifecycle、inbound、outbound、media、streaming、commands；`backend/utils/` 负责限流、渲染与 live 编辑；声明 `uses_bot_commands` |
| `plugins/qq/`（QQ（NapCat）） | `qq` | 每个账号使用插件私有的托管 NapCat 进程和登录目录；仅在验证出 QQ 号后写入 `plugin-data/qq/accounts.json`（归属、响应规则和内部 OneBot endpoint/令牌），扫码中的临时连接关闭时清理，异常退出的残留目录在下次加载时清理 |
| `plugins/qqbot/` | `qqbot` | `channel.py` 只做组合与启停，Gateway、C2C 入站、HTTP/媒体出站、live stream 分属各 mixin |
| `plugins/feishu/` | `feishu` | lark-oapi 长连接跑在独立线程和私有事件循环（`ws.py`），回调只去重并交回宿主循环；REST 在 `api.py`，入站解析在 `inbound.py`，CardKit 流式卡片在 `streaming.py` |

QQ 群会话的规范 chat_id 是 `gqq:<群号>`，裸号一律是私聊。渠道插件配置位于 `[plugins.<id>]`；旧的 `[channels.telegram]` / `[channels.qq]` 配置已移除，不再自动迁移。新增渠道的写法见 `docs/_handbook/channel-plugins.md`。

## 标识与投递

`session_key.py`、`reply_context.py` 和公共 channel identifier helper 负责稳定定位账号、聊天、线程与回复上下文。群聊过滤和成员隔离必须在入站边界明确处理。typing、流式编辑等辅助动作允许独立失败，但最终消息投递和权威会话写入必须可观测。

「谁能和角色说话」由接收账号的响应规则决定（私聊/群聊开关、群聊需要 @、黑名单，均为账号级设置，所有群聊共用），规则连同账号身份、所属角色和凭据保存在账号所属插件自己的存储里，宿主只在内存里按已加载插件登记的账号建索引（#450）。入站准入由 `ChannelHub` 统一判断：接收账号属于某个角色、其插件已加载且在线，发送者不在账号黑名单里即放行；黑名单条目按发送者 ID 精确匹配，或按渠道别名（Telegram 用户名）忽略大小写匹配；`/stop` 走同一准入。`/chatid`（别名 `/myid`）由各渠道插件自己回复会话类型与号码，不进入角色对话。

## 修改影响

- 修改 Channel 合约或钩子：检查全部渠道插件、`start_channels`/ChannelHost、`channel_directory`、消息总线、测试替身，以及 `docs/_handbook/plugin-runtime-contract.md` 的 Runtime API 版本。
- 修改聊天标识：检查角色绑定、Session/Conversation 键、群聊记忆域和推送目标。
- 修改账号响应规则：检查插件的规则保存钩子（`ctx.accounts.on_rules_change`）、入站准入和账号详情里的规则编辑器。
- 修改附件模型：检查 Telegram 媒体、QQ 适配、桌面桥接、自动 CG 和历史消息展示。
- 修改 QQ 渠道：NcatBot 需同步检查主 loop/bot loop 桥接、群聊过滤和 CQ 媒体；QQBot 需同步检查 Gateway intent、token/REST、C2C message id 和 live stream 状态。
- 新增渠道：写成渠道插件（manifest 声明 + 配置模型 + Channel 合约），复用 `ChannelIntake`、会话键解析和输出端口，不复制 Agent 回合逻辑；步骤见 `docs/_handbook/channel-plugins.md`。
