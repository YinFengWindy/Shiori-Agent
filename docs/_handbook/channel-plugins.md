# 写一个渠道插件

所有外部聊天渠道（Telegram、QQ（NapCat）、官方 QQBot、飞书）都是插件，宿主只拥有 `desktop`。本篇按「新增一个渠道」的顺序说明要写什么；通用插件机制（能力、作用域、热卸载）见 [插件开发](plugins-tutorial.md)，版本化契约见 [Runtime Contract](plugin-runtime-contract.md)。

现有实现可以直接对照：

| 插件 | 适合参考 |
| --- | --- |
| `plugins/qqbot/` | 结构最紧凑：Gateway + REST，mixin 拆分入站、出站、流式 |
| `plugins/telegram/` | 轮询连接、bot 命令菜单（`uses_bot_commands`）、编辑消息式流式预览 |
| `plugins/qq/` | 第三方 SDK 带进程级全局配置时，如何在换代时写入与恢复 |
| `plugins/feishu/` | SDK 自带线程和事件循环时的线程模型、CardKit 流式卡片、`status()` |

## 1. 包布局与 manifest

```text
plugins/demo_chat/
  manifest.yaml
  backend/
    plugin.py        # setup + 配置模型
    channel.py       # 渠道对象
  tests/
  pyproject.toml
  TESTING.md
```

```yaml
api: 2
id: demo_chat
display_name: Demo Chat
version: '0.1.0'
desc: Demo Chat 渠道
capabilities:
  - channels
  - accounts
  - kv
  - rpc
channels:
  - name: demo_chat                 # 渠道名：会话线程与账号路由的数据键
    label: Demo Chat                # 账号面板和消息来源里显示的名字
    contact_label: 用户 ID           # 可选，群聊响应规则里成员 ID 的说明
    chat_types:                     # 必填，渠道支持的会话类型
      - type: private               # private / group
        label: 私聊                  # 类型下拉里的名字
        chat_id_label: 用户 ID       # 会话标识的标签
        chat_id_hint: 对方的用户 ID   # 可选，会话标识的提示
        prefix: 'dm:'               # 可选，拼在号码前组成存储的 chat_id
```

- 插件 id 建议与渠道名相同。渠道名写进会话线程，账号 ID 为 `<插件 id>:<平台账号>`；**发布后不能改名**，否则历史账号和线程无法定位。
- 声明是静态的：插件停用、未授信或还没有账号时，桌面端也能通过 `channels.list` 列出这个渠道并标注状态。插件加载后再从自己的存储恢复账号。
- `chat_types` 必须声明（Runtime API 2.5，规则见[运行时契约](plugin-runtime-contract.md#runtime-api-22-channel-declarations)），缺失时宿主拒绝整个 manifest；按类型的 `prefix` 拼出存储的 `chat_id`。
- `ctx.channels.add()` 只接受本 manifest 声明过的名字；两个插件声明同一个名字会同时变成 `CONFLICT`。规则细节见 [渠道声明](plugins-tutorial.md#渠道声明)。

## 2. 账号存储与连接

渠道插件保存每个账号的身份、所属角色、响应规则和凭据。宿主只保留已加载账号的内存索引；`[plugins.<id>]` 只用于插件启停及与账号无关的插件设置。现有实现可对照 `plugins/telegram/backend/bots.py`、`plugins/qq/backend/accounts_runtime.py`、`plugins/qqbot/backend/accounts.py` 和 `plugins/feishu/backend/plugin.py`。

- `setup` 始终贡献 manifest 声明的渠道。多账号渠道可用 `AccountChannelGroup` 管理账号连接，新增或断开账号不需要重载运行时。
- 插件从 `ctx.kv` 或自己的工作区存储读取账号；恢复时先用 `ctx.accounts.role_exists(role_id)` 清理所属角色已删除的账号，再用 `register_saved(...)` 登记。读取失败或无效数据用 `reject(...)` 报告，不影响其它账号。
- 新增账号前校验平台身份，并用 `ctx.accounts.check_owner(...)` 检查角色与账号归属；插件保存数据后用 `register(...)` 登记，再按连接状态调用 `report(...)`。账号 ID 由宿主生成，格式为 `<插件 id>:<平台账号>`。
- 宿主对头像只有一条约定：`register(..., avatar_url=...)` / `register_saved(...)` 的 `avatar_url` 必须是空字符串（无头像），或不超过 256 KiB、内容与声明类型一致的 PNG/JPEG/GIF/WebP base64 `data:image/...` URI，否则登记被拒绝（远程 URL 同样被拒）。头像的获取、编码和缓存都由插件自己完成：插件在后台下载平台头像、自行转成 data URI 并存进插件存储，下载失败保留已存头像且不影响连接；后台任务由插件自己持有，并在断开、删除或停止时取消。
- 账号的连接、错误、昵称或头像实际变化（以及登记、移除）时，宿主向桌面端推送 `accounts.updated` 事件（payload `{"account_id": ...}`）；报告与之前相同时不推送。
- 登记 `on_delete(...)`，提供断开连接与清除插件存储的计划；角色删除时宿主也会调用它。登记 `on_rules_change(...)`，把宿主编辑的响应规则写回同一份账号记录。账号创建、编辑和连接通过插件 RPC 与角色页中的账号界面协作。
- 若插件还有不属于某个账号的全局设置，可单独声明 `config_model`，由「设置 › 插件」的自动表单编辑；账号凭据不放在该模型或 `config.toml` 中。

## 3. 渠道对象契约

协议定义在 `apps/backend/infra/channels/contract.py`。必需部分：

```python
class DemoChatChannel:
    name = "demo_chat"

    async def start(self, ctx: ChannelContext) -> None: ...
    async def stop(self) -> None: ...
    def pause_intake(self) -> None: ...
    def resume_intake(self) -> None: ...

    @property
    def configuration_key(self):
        """跨代复用判断：值不变时宿主复用旧连接，新构造的实例立即被 stop。"""
        return ("demo_chat", self._app_id, self._app_secret)
```

- **启停归宿主**。ChannelHost 负责 `start`/`stop` 和换代，不要用 `ctx.background` 自己起连接。
- **`configuration_key`**：保存任何设置都会准备新运行代。key 与上一代相同的渠道直接复用旧连接（不断线），宿主会对新构造但没用上的实例调用一次 `stop()`，所以**构造函数不能产生流量**，连接只在 `start` 里建立。key 应覆盖所有会影响连接的设置；不提供 key 的渠道每次换代都会重建。
- **`start` / `stop` 要可重复调用**：`stop` 对从未启动的实例也要安全；换代失败回滚时，宿主会对已停止的旧实例再次调用 `start`。`start` 里订阅和注册要用标志位防止重复（参考飞书的 `_events_bound`、`_outbound_bound`）。
- **入站闸门**：换代期间宿主先 `pause_intake()`，新连接以 `ctx.intake_paused=True` 启动，发布后再 `resume_intake()`。用 `infra.channels.intake.ChannelIntake` 实现即可：它在暂停时缓冲入站消息，溢出或关闭时回复「渠道配置正在切换」提示，`stop` 时调用 `close()` 排空。
- **`stop` 的顺序**：先切断新工作的来源（暂停入站、退订事件、断开连接），再取消或等待在途任务，最后注销出站与推送注册。

`ChannelContext` 提供本代的宿主服务：`bus`（消息总线）、`session_manager`、`event_bus`、`push_tool`（`message_push` 工具）、`attachment_store`（入站媒体落盘）、`http_resources`、`interrupt_controller`（`/stop`）、`bot_commands`、`log`、`channel_hub`（账号准入与路由）、`intake_paused`。

## 4. 入站、会话键与 chat_id 约定

一条入站消息的标准处理顺序（飞书 `_handle_message` / `_accept_inbound`）：

1. 解析平台事件，按平台消息 id 去重（重投很常见，`infra.channels.base.MessageDeduper` 或自带的过期集合）。
2. 构造 `InboundMessage(channel=self.name, sender=<平台用户 id>, chat_id=<会话 id>, content=..., media=[本地路径], metadata={...})`。`metadata` 必须带已登记的 `account_id`，并带 `message_id` / `external_message_id`（宿主用它在线程里去重）；能确定时带 `chat_type`、`mentioned` 和发送者别名 `username`。同时在 `metadata["via_account"]` 附上接收账号的快照（见下文「经由账号快照」）。
3. 交给 `ChannelIntake.submit()`；真正接收时：
   - `ctx.channel_hub.is_sender_allowed(channel=, chat_id=, sender_id=, account_id=)` 为假就丢弃。只有已登记、在线且所属角色存在的接收账号能处理消息。
   - `message = ctx.channel_hub.route_account_inbound(message)`：按该账号的私聊/群聊开关、需要 @ 与黑名单准入，所有群聊共用这组账号级设置；返回 `None` 就丢弃，否则补上 `role_id`、`thread_id`、`session_key_override` 等元数据。
   - `metadata["conversation_duplicate"]` 为真时丢弃，否则 `await ctx.bus.publish_inbound(message)`。

约定：

- **chat_id 是渠道本地的会话标识**，必须稳定。一个渠道有多种会话类型时用前缀区分，例如 QQBot 的 `c2c:<openid>` / `group:<openid>`、QQ（NapCat）群聊的 `gqq:<群号>`。
- **访问控制由接收账号的响应规则决定**。插件将规则与账号一起保存，入站时交给 `ChannelHub` 判断；黑名单支持发送者 ID 与忽略大小写的渠道别名（如 Telegram 用户名）。`/stop` 等控制命令走同一账号准入。`/chatid`（别名 `/myid`）由渠道插件自己识别并回复会话类型与号码，不进入角色对话。
- **会话键**：准入后的消息用所属角色的 `role:<role_id>`（路由写进 `session_key_override`）。出站处理和流式状态统一用 `infra.channels.session_key.resolve_outbound_session_key(msg, default_channel=self.name)` 计算，与 `TurnStarted` / `StreamDeltaReady` 的 `session_key` 对齐。
- 用户引用了一条历史消息时，用 `infra.channels.reply_context.build_inbound_text_with_reply_context()` 拼进正文，保持各渠道的格式一致。

### 经由账号快照

契约定义在 `apps/backend/core/accounts/models.py`：`ViaAccount` 与元数据键 `VIA_ACCOUNT_KEY = "via_account"`。快照描述消息当时经由的账号，由插件自己构造，宿主原样存进消息元数据，不回头查账号索引，所以账号删除后历史消息里的快照照样可读；旧消息没有快照时不显示，也不回填。

```python
ViaAccount(
    platform="qq",                  # 与 register(...) 的 platform 一致
    platform_account_id="101",      # 与 register(...) 的 platform_account_id 一致
    display_name="小栞",             # 当时的显示名，可为空字符串
    prefix="QQ 号「小栞」（101）",     # 插件按平台习惯写好的来源文案
).to_metadata()
```

- 三条路径都要带：入站消息的 `metadata["via_account"]`；回复送达后 `channel_hub.mark_delivery(..., via_account=...)`（只在 `sent` 时传）；`account.send` 的返回值 `{"message_id": ..., "via_account": ...}`。
- 快照描述送达时经由的账号。平台接受消息之后，取快照这一步不能再失败：快照若来自内存里的连接状态（如 Telegram、飞书的机器人名），发送后在 `mark_delivery` 时取即可；若要读可能被并发删除的存储（如 QQ 的账号配置、QQBot 的应用记录），就在发送前取好。
- 宿主用同一套规则（`ViaAccount.for_account`）校验三条路径的快照：形状正确，且 `platform` / `platform_account_id` 与该账号登记的一致。入站快照不合格时拒收这条消息；发送后的快照（`mark_delivery`、`account.send` 回执）不合格时，消息照常记为已发送，只是不带快照，宿主记一条 error 日志指出插件缺陷。
- 模型看到的来源前缀直接使用 `prefix`：`[消息来源: {...}；经由账号: QQ 号「小栞」（101）]`。现有文案：QQ `QQ 号「昵称」（QQ 号）`、QQBot `QQ 机器人「机器人名」（AppID ...）`、Telegram `Telegram 机器人「名称」（@用户名）`、飞书 `飞书应用「应用名」（<区域>:<app_id>）`。

### 身份配对与「你的用户」

桌面端用户在「我的身份」里生成一次性配对码（10 分钟有效，只存在内存中，重启后失效），再用自己的平台账号私聊发给任一角色的账号，宿主据此记住用户在该平台的身份（`core/identity`，存于工作区 `user_identities.json`）。插件只负责：

- **识别私聊并声明作用域**：私聊消息交给 `route_account_inbound` 之前，调用 `core.channels.pairing_command.answer_pairing_code(hub, message, scope=..., send=...)`；返回 `True` 时丢弃这条消息（不进入会话、不触发角色回复），宿主已经通过 `send` 回复「已绑定」。群聊消息不调用。`message.sender` 是要绑定的平台用户 ID，`message.metadata` 必须带接收账号的 `account_id`。
- **`scope` 按平台决定**：`"platform"` 表示用户 ID 在整个平台内唯一（QQ 号、Telegram 用户 ID），绑定对该插件的所有账号生效；`"account"` 表示 ID 只对接收它的应用有效（飞书 open_id、QQBot openid），绑定只对这个账号生效。

其余由宿主完成：`ChannelHub.claim_pairing` 校验配对码（错误、过期、已用都不绑定）并记下配对所在的私聊；`route_account_inbound` 给已绑定的发送者（按作用域匹配）写入 `metadata["sender_is_user"] = True`（插件自带的该字段会被丢弃），来源前缀随之显示 `；发送者: 你的用户`，并记下这位用户之后私聊过的会话。

删除账号（包括删除角色时随之删除的账号）会移除只对该账号生效的绑定，并从平台级绑定里去掉这个账号的私聊记录；同一账号重新添加后需要重新配对。

用户不在桌面前时，主动推送可以按在场与最近对话规则选中这些私聊，经 `account.send` 以 `target_kind="private"`、`target_id=<平台用户 ID>` 投递。因此**绑定的平台用户 ID 必须能直接作为该账号的私聊发送目标**。

## 5. 出站与 `message_push`

```python
async def start(self, ctx):
    ctx.bus.subscribe_outbound(self.name, self._on_response)
    ctx.push_tool.register_channel(
        self.name,
        text=self.send,
        image=self.send_image,
        file=self.send_file,
        description="Demo Chat，私聊 chat_id 格式为 dm:<用户 ID>",
    )

async def stop(self):
    self._bus.unsubscribe_outbound(self.name, self._on_response)
    self._push_tool.unregister_channel(self.name, text=self.send)
```

- `subscribe_outbound` 接收 Agent 回合的最终回复（`OutboundMessage`）。发送成功或失败后调用 `ctx.channel_hub.mark_delivery(msg, default_channel=self.name, delivery_status="sent"|"failed", external_message_id=..., via_account=...)`，让会话里的消息状态正确；`via_account` 只在 `sent` 时传发送账号的快照。
- **群聊被动回复点名触发者**：回复的 `msg.metadata` 带着触发消息的元数据（`chat_type`、`sender_id`、`external_message_id` 等）。`chat_type` 为群聊（`core.common.channel_chat_types.is_group_chat_type`）时，插件按平台惯例点名触发者：QQ 在开头 @ 发送者，Telegram 回复触发消息。模型额外选择要 @ 的成员放在 `metadata["mention_ids"]`（键名 `REPLY_MENTION_IDS_KEY`，只有群聊回复会带），插件一并提及；其中平台用不了的 ID 记 warning 后跳过，回复照常发出（触发者仍被点名）。私聊回复不受影响；没有群聊的渠道忽略这些字段。
- `register_channel` 让模型能用 `message_push` 主动发消息。`description` 会写进工具描述的「当前可用渠道」列表，用一句话说明渠道身份和 chat_id 格式；工具描述只列出当前已注册、未停用的渠道。
- `unregister_channel` 传入自己的 `text` 回调，只注销本实例的注册，不会误删换代后新连接的注册。

### 账号目标发送（`account.send` / `account.targets`）

模型通过宿主的 `account_list`、`account_targets`、`account_send` 工具和 `message_push` 改投使用账号，参数里只有渠道 ID（插件 ID），宿主按「每个渠道一个账号」找到当前角色的账号，再以 `account_id` 调用插件 RPC。常量与请求形状在 `apps/backend/core/accounts/target_contract.py`：

- `account.targets` 收到 `account_id`、`kind`、`group_id`、`member_id`。
- `account.send` 收到 `account_id`、`message`，以及 `AccountTarget.to_payload()`：`target_kind`、`target_id`、`message_thread_id`（整数或 `None`）、`group_id`（仅 `group_member`，否则为空字符串）、`mention_ids`（仅 `group`，可为空列表）。
- 宿主只校验形状：`mention_ids` 只能用于 `target_kind="group"`；`target_kind="group_member"`（群临时会话，`target_id` 为成员 ID）必须带 `group_id`。平台能不能做由插件判断，做不到时明确报错，例如 QQBot、飞书没有群聊，收到 `mention_ids` 或 `group_member` 直接拒绝；Telegram 支持提及但没有群临时会话。
- 返回平台真实的 `message_id`；拿不到回执时抛 `UncertainDeliveryError`，宿主把尝试记为「不确定」。

## 6. 可选钩子

核心不按渠道名写死策略，而是询问渠道对象的可选钩子，表格与默认值见 [渠道钩子](plugins-tutorial.md#渠道钩子runtime-api-23)。实践要点：

- `supports_stream_events(chat_id)`：只对真能实时展示的会话返回 `True`（Telegram 和 QQBot 只开私聊）。返回 `True` 就必须消费流式事件，见下一节。
- `system_prompt_hint(chat_id)`：只写渲染限制和渠道身份这类硬规则（例如 Telegram 禁止 Markdown 表格、QQBot 提醒主动推送用 `channel=qqbot`），保持简短，它每轮都会进系统提示词。
- `default_chat_type`：只支持私聊的渠道写 `"private"`，入站没带 `chat_type` 时由路由补上。
- `uses_bot_commands = True`：只有在 `start` 里读取 `ctx.bot_commands`（如注册 Telegram 命令菜单）的渠道才声明；宿主会把命令列表并入复用键，其它插件增减命令时它才会重连。
- `status()`：返回 `{"connected": bool, "account": str, "detail": str}`（后两项可省略），`channels.list` 原样带给桌面端。适合放机器人名称、断线原因或账号连接状态。`status()` 抛错时渠道显示为 `failed`。

这些钩子和 `description` 参数属于 Runtime API 2.3；外部包要声明 `runtime_api: ">=2.3.0 <3.0.0"`。

## 7. 流式回复

开启 `supports_stream_events` 后，回合会在事件总线上发布 `TurnStarted`、`StreamDeltaReady`（以及 `ToolCallStarted` / `ToolCallCompleted`）。通用模式：

1. `start` 里 `ctx.event_bus.on(EventType, handler)`，`stop` 里 `off`；handler 先按 `event.channel == self.name` 过滤。
2. `TurnStarted` 时为该 `session_key` 建立 live 状态；`StreamDeltaReady` 只追加缓冲，由单个任务按最小间隔合并刷新，同一会话最多一个在途请求，平台限流时退避而不是丢字。
3. 最终回复**仍然经 `subscribe_outbound` 送达**。收到 `OutboundMessage` 时先让 live 状态用最终全文收尾；没有 live 消息（流式失败或从未开始）就按普通消息发送。流式是尽力而为的预览，最终投递必须可靠、可观测。
4. `stop` 时取消 live 任务并收尾未完成的消息。

三种平台做法：

- Telegram（`plugins/telegram/backend/channel/streaming.py`、`backend/utils/live_edit.py`）：先发一条消息再反复编辑，工具调用显示为尾部状态行。
- QQBot（`plugins/qqbot/backend/streaming.py`）：C2C 流式消息接口，按 `stream_msg_id` + 递增 `index` 分片提交。
- 飞书（`plugins/feishu/backend/streaming.py`）：CardKit 流式卡片，每轮一张卡片实体，全文替换由客户端打字机式展示；缺少权限时退回普通卡片。

## 8. 线程与第三方 SDK

- 渠道代码默认跑在宿主事件循环上。SDK 自带线程或事件循环时（飞书的 lark-oapi 长连接），把连接放到独立线程，回调里只做去重并用 `loop.call_soon_threadsafe` 交回宿主循环，网络与路由都在宿主循环上完成；`stop` 必须有超时，不能让宿主挂起。
- SDK 有进程级全局配置时（NcatBot），每次激活都显式写入本代的值，留空时恢复 SDK 原值，避免上一代的设置残留到下一代（`plugins/qq/backend/channel/lifecycle.py`）。
- 第三方依赖写进插件 `pyproject.toml` 的 `dependencies`；桌面安装包由宿主的 `apps/backend/requirements/production.txt` 统一打包，新依赖要同时加到那里。
- 渠道插件应保持 `supports_hot_unload: true`（默认值），否则任何设置保存都会要求重启应用。

## 9. 测试

测试放在 `plugins/<id>/tests/`，文件与 `backend/` 模块对应，全程不联网：

- **账号与 setup**：用 `shiori_plugin_testkit.packages.stage_plugin_package` 把包暂存到临时目录，交给 `PluginKernel`；断言渠道声明保持可见、插件能从自己的存储恢复账号、清理已删除角色的账号，并将无效账号单独报告（参考 `plugins/telegram/tests/test_plugin.py`）。
- **渠道行为**：平台 REST 用 `httpx.MockTransport` 替代，长连接用假连接；`ChannelContext` 直接构造，`channel_hub`、`push_tool` 可用简单替身（参考 `plugins/feishu/tests/conftest.py`）。至少覆盖：未登记、离线或无所属角色的接收账号被拒绝，响应规则准入、入站去重、`pause_intake` 期间缓冲、`stop` 对未启动实例安全、流式收尾与失败回退。
- **真实运行时**：testkit 的 `plugin_runtime` fixture 启动隔离的 `AppRuntime` 和桌面服务，可用于验证设置保存、热换代。
- `pyproject.toml` 声明 `test = ["shiori-plugin-testkit==0.1.0"]` extra 和 pytest 配置（`-W error`、`asyncio_mode = "auto"`），`TESTING.md` 写明仓库外运行方式和真机验收清单。

仓库内运行 `uv run pytest plugins/<id>/tests`；合并前用隔离环境验收：

```sh
uv run python scripts/verify_plugin_tests.py --plugins <id>
```

它从副本构建非 editable wheel、在干净 venv 里跑插件测试并审计模块来源，细节见 [插件测试](../agents/plugin-testing.md)。

## 10. 检查清单

- [ ] manifest 声明 `channels`、`accounts` 能力和渠道，渠道名与插件 id 一致且今后不改。
- [ ] 凭据和响应规则只存于插件账号记录；恢复时清理已删除角色的账号，缺少凭据的账号独立报告连接状态。
- [ ] 构造函数不产生流量；`configuration_key` 覆盖全部连接设置。
- [ ] `start`/`stop` 可重复调用；`stop` 先断来源再排空任务；出站和推送注册在 `stop` 里撤销。
- [ ] 入站带已登记的 `account_id`，经 `is_sender_allowed(..., account_id=...)` → `route_account_inbound` → 去重 → `publish_inbound`；用 `ChannelIntake` 处理换代暂停。
- [ ] 入站、回复送达和 `account.send` 回执都附上 `ViaAccount` 快照；不支持的 `mention_ids` / `group_member` 明确报错。
- [ ] 私聊入站在路由前交给 `answer_pairing_code` 并声明 `scope`；绑定的平台用户 ID 可直接作为 `account.send` 的私聊目标。
- [ ] 开了流式就消费事件并在最终回复时收尾；失败时退回普通发送。
- [ ] `register_channel(..., description=)` 写清 chat_id 格式。
- [ ] 测试离线，`verify_plugin_tests.py --plugins <id>` 通过。
