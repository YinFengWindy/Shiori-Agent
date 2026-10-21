---
title: 渠道系统
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - packages/sdk/python/shiori_sdk/channels/
  - apps/backend/infra/channels/
  - apps/backend/core/channels/hub.py
  - apps/backend/core/common/channel_directory.py
  - apps/backend/core/identity/
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

外部渠道全部由插件提供，宿主只拥有 `desktop`，不再有内置渠道或「频道」设置分区（#363）。`packages/sdk/python/shiori_sdk/channels/` 定义 Channel 合约、可选钩子与 `ChannelContext`；插件在 manifest 静态声明渠道，`setup` 里经 `ctx.channels.add()` 贡献实例。`apps/backend/bootstrap/channels.py` 的 `start_channels` 只装配插件贡献的渠道：构造共享上下文，按 `configuration_key`（声明 `uses_bot_commands` 的渠道再加上 bot 命令列表）跨代复用未变的连接；`bootstrap/channel_host.py` 负责启停、换代时的入站暂停与回滚、已移除连接的排空。`apps/backend/infra/channels/` 放宿主侧渠道基础设施：`account_group.py`（按账号增删成员连接的渠道组）、`intake.py`（`ChannelIntake`，配置切换期间的有界入站缓冲）和 `base.py`（媒体落盘的 `AttachmentStore`）。`apps/backend/core/channels/hub.py` 做账号准入与入站路由，`core/common/channel_directory.py` 按渠道名向已发布的连接查询钩子。`desktop_bridge/runtime/channel_listing.py` 的 `channels.list` 把 `desktop` 与各插件的静态声明合并上运行状态，供角色绑定面板使用。渠道配置在各自的 `[plugins.<id>]`，由「设置 › 插件」的自动表单编辑。

| 插件 | 渠道名 | 结构 |
| --- | --- | --- |
| `plugins/telegram/` | `telegram`（私聊、群聊） | `backend/channel/` 拆分 lifecycle、polling、inbound、outbound、media、streaming、commands；`backend/utils/` 负责限流、渲染与 live 编辑；声明 `uses_bot_commands` |
| `plugins/qq/`（QQ（NapCat）） | `qq`（私聊、群聊，声明 `group_listening`） | 每个账号使用插件私有的托管 NapCat 进程和登录目录；仅在验证出 QQ 号后写入 `plugin-data/qq/accounts.json`（归属、响应规则和内部 OneBot endpoint/令牌），扫码中的临时连接关闭时清理，异常退出的残留目录在下次加载时清理 |
| `plugins/qqbot/` | `qqbot`（仅私聊，chat_id 前缀 `c2c:`） | `channel.py` 只做组合与启停，Gateway（`gateway.py`）、C2C 入站（`inbound.py`）、HTTP/媒体出站（`outbound.py`）、live stream（`streaming.py` / `stream_delivery.py`）分属各 mixin |
| `plugins/feishu/` | `feishu`（仅私聊） | lark-oapi 长连接跑在独立线程和私有事件循环（`ws.py`），回调只去重并交回宿主循环；REST 在 `api.py`，入站解析在 `inbound.py`，CardKit 流式卡片在 `streaming.py` |

QQ 群会话的规范 chat_id 是 `gqq:<群号>`，裸号一律是私聊。渠道插件配置位于 `[plugins.<id>]`；旧的 `[channels.telegram]` / `[channels.qq]` 配置已移除，不再自动迁移。新增渠道的写法见 `docs/_handbook/channel-plugins.md`。

## 标识与投递

自然聊天的普通渠道回复使用逐条确认的序列（#866）：角色模型仍由同一角色的 gate 串行执行，入站 dispatcher 按聊天排队；仅在两条消息间的等待让出角色 gate，等待期间不持 bus transport lock。每段进入原 channel lane，渠道在其 90 秒单条边界内完成平台请求与回执，队列接收不代表已发送。当前段的 pending / failed / uncertain 行保留投递记录，Session 历史与 ContextView 统一排除未确认正文；已执行工具单独保留。换代入口取消旧代序列尾部，已开始的平台发送及记账收尾后释放 runtime lease。桌面交互序列仍走自己的 commit/event 路径。

SDK 的 `shiori_sdk.channels.session_key`、`shiori_sdk.channels.reply_context` 和公共 channel identifier helper 负责稳定定位账号、聊天、线程与回复上下文。群聊过滤和成员隔离必须在入站边界明确处理。typing、流式编辑等辅助动作允许独立失败，但最终消息投递和权威会话写入必须可观测。

自然聊天插话（#867）只处理既有准入和去重后进入 dispatcher 的普通输入。以角色、接收账号、渠道、群/私聊、聊天、Telegram 话题和真实 sender 定位回复计划；同一发送者补充在入队时使旧计划失效，其他群友仍按该聊天顺序等待。生成中的计划在当前模型/工具步骤结束后交接，不再开启后续工具或总结调用；已接纳输入和已完成工具事实入库，未发送正文不入历史。发送中的单条请求和记账继续受保护，已发前缀保留。注册由具体计划和运行时代持有，旧任务只释放自身注册；角色移除或能力关闭后，下一个安全边界丢弃剩余计划。

「谁能和角色说话」由接收账号的响应规则决定（私聊/群聊开关、黑名单，均为账号级设置，所有群聊共用），规则连同账号身份、所属角色和凭据保存在账号所属插件自己的存储里，宿主只在内存里按已加载插件登记的账号建索引（#450）。入站准入由 `ChannelHub.route_account_inbound` 统一判断：接收账号属于某个角色、其插件已加载且在线、对应私聊/群聊开关打开，发送者不在账号黑名单里即放行；黑名单条目按发送者 ID 精确匹配，或按渠道别名（Telegram 用户名）忽略大小写匹配；`/stop` 走同一准入。群聊里只有「点名」账号的消息（SDK `addresses_account`：插件标记了 @ 本账号，或上报的被回复者 `reply_to_sender_id` 等于账号自己的平台 ID）才开启回合（#537）；未点名的群消息在角色旁听该群时存进旁听记录（#538，渠道需在 manifest 声明 `group_listening`，目前只有 QQ），否则丢弃。`reply_to_sender_id` 目前只有 QQ 上报，Telegram 只认 @。

渠道 `/stop` 通过 `InterruptController.request_interrupt` 控制面传入接收账号 `account_id`、`chat_type`、`message_thread_id` 和渠道/chat；宿主与入站回合共用 `turn_tracking_key` 精确定位，Telegram 的不同话题不会因为共享 chat ID 而互相停止。只有未携带来源扩展的旧任务保留 session-only 唯一任务兼容，部分来源不能兜底匹配到账号/话题任务。桌面按原 session/turn 所有权停止（#867 / PR #880）。

发送者若是桌面用户已绑定的平台身份（`core/identity/`，用户在私聊里向角色账号发送一次性配对码完成绑定，SDK `pairing_command.answer_pairing_code` 处理），宿主会在元数据里标记 `sender_is_user`（引用到用户时标记 `reply_to_sender_is_user`），插件不能自行声明；与用户的私聊会被记住，作为主动消息经该账号送达用户的落点。`/chatid`（旧别名 `/myid`）由渠道插件在入站处理中识别（与 `/stop` 同层、早于 hub 准入），交给 SDK `chat_id_command.answer_chat_id_command` 回复会话类型与号码，不进入角色对话；目前 Telegram、QQBot、飞书接入了该命令，QQ（NapCat）插件未接入。

## 修改影响

- 修改 Channel 合约或钩子：检查全部渠道插件、`start_channels`/ChannelHost、`channel_directory`、消息总线、测试替身，以及 `docs/_handbook/plugin-runtime-contract.md` 的 Runtime API 版本。
- 修改聊天标识：检查角色绑定、Session/Conversation 键、群聊记忆域和推送目标。
- 修改账号响应规则：检查插件的规则保存钩子（`ctx.accounts.on_rules_change`）、入站准入和账号详情里的规则编辑器。
- 修改附件模型：检查 Telegram 媒体、QQ 适配、桌面桥接、自动 CG 和历史消息展示。
- 修改 QQ 渠道：需同步检查 `QQAccountsRuntime` 的账号生命周期、`OneBotSocket` 的连接清理、群聊过滤和 CQ 媒体；QQBot 需同步检查 Gateway intent、token/REST、C2C message id 和 live stream 状态。
- 新增渠道：写成渠道插件（manifest 声明 + 配置模型 + Channel 合约），复用 `ChannelIntake`、会话键解析和输出端口，不复制 Agent 回合逻辑；步骤见 `docs/_handbook/channel-plugins.md`。
