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
  - config
  - channels
config_model: DemoChatConfigModel
channels:
  - name: demo_chat                 # 渠道名：角色绑定与会话线程的数据键
    label: Demo Chat                # 绑定面板和消息来源里显示的名字
    contact_label: 用户 ID           # 可选，群聊绑定黑名单里成员 ID 的说明
    chat_types:                     # 必填，渠道支持的会话类型
      - type: private               # private / group
        label: 私聊                  # 类型下拉里的名字
        chat_id_label: 用户 ID       # 号码输入框的标签
        chat_id_hint: 对方的用户 ID   # 可选，号码输入框的占位提示
        prefix: 'dm:'               # 可选，拼在号码前组成存储的 chat_id
```

- 插件 id 建议与渠道名相同。渠道名写进 `roles.json` 的绑定和会话线程，**发布后不能改名**，否则历史绑定和线程都会变成孤儿。
- 声明是静态的：插件停用、未授信或还没填凭据时，桌面端也能通过 `channels.list` 列出这个渠道并标注状态，用户可以先绑定再填凭据。
- `chat_types` 必须声明（Runtime API 2.5，规则见[运行时契约](plugin-runtime-contract.md#runtime-api-22-channel-declarations)），缺失时宿主拒绝整个 manifest：绑定面板让用户先选类型再填号码，按类型的 `prefix` 拼出存储的 `chat_id`，保存时宿主校验两者一致。
- `ctx.channels.add()` 只接受本 manifest 声明过的名字；两个插件声明同一个名字会同时变成 `CONFLICT`。规则细节见 [渠道声明](plugins-tutorial.md#渠道声明)。

## 2. 配置模型与自动表单

```python
# backend/plugin.py
import re
from pydantic import BaseModel, Field, field_validator

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class DemoChatConfigModel(BaseModel):
    """``[plugins.demo_chat]``：凭据明文存 TOML，支持 ``${ENV}``。"""

    app_id: str = Field(default="", title="App ID", description="开发者后台的应用 ID")
    app_secret: str = Field(
        default="", title="App Secret", description="支持 ${ENV} 引用环境变量"
    )

    @field_validator("app_id", "app_secret", mode="before")
    @classmethod
    def _normalize_credential(cls, value: object) -> str:
        # 宿主已展开 ${ENV}；仍是占位符说明变量缺失，按未配置处理。
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx):
    """凭据齐备时贡献渠道；凭据不全直接 return，渠道显示为「未配置」。"""
    config = DemoChatConfigModel.model_validate(ctx.config.as_dict())
    if not config.app_id or not config.app_secret:
        return
    from .channel import DemoChatChannel  # 有凭据才导入 SDK，降低未启用时的启动开销

    ctx.channels.add(DemoChatChannel(config.app_id, config.app_secret))
```

- 声明了 `config_model` 的插件自动在「设置 › 插件」下得到一个表单子标签，不必写 `ui/index.tsx`。字段的 `title` 是标签，`description` 是提示。
- **密码框按字段名判断**：字符串字段名（不区分大小写）含 `secret`、`token` 或 `password` 时渲染为可切换显示的密码框（`apps/desktop/renderer/src/plugins/jsonSchemaForm.ts`）。所以凭据字段应命名为 `app_secret`、`token`、`ws_token` 这类名字，而不是 `key`。
- **`${ENV}`**：宿主读取 `[plugins.<id>]` 时展开 `${VAR}`，环境变量不存在时再尝试工作区 `memory/<VAR>` 文件；都没有时占位符原样传给插件。插件应把未展开的占位符当作未配置（上面的 validator），不要拿它去连服务。写回 TOML 时占位符保持原样，密钥不会被展开后落盘。
- `enabled` 由宿主拥有，不要放进模型。其它字段的合法性在 `setup` 里用 `model_validate` 校验，校验失败由内核回滚为 `FAILED`。
- 密钥明文存在 `config.toml`（或经 `${ENV}` 引用），目前没有 keyring 集成。

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

`ChannelContext` 提供本代的宿主服务：`bus`（消息总线）、`session_manager`、`event_bus`、`push_tool`（`message_push` 工具）、`attachment_store`（入站媒体落盘）、`http_resources`、`interrupt_controller`（`/stop`）、`bot_commands`、`log`、`channel_hub`（角色绑定与路由）、`intake_paused`。

## 4. 入站、会话键与 chat_id 约定

一条入站消息的标准处理顺序（飞书 `_handle_message` / `_accept_inbound`）：

1. 解析平台事件，按平台消息 id 去重（重投很常见，`infra.channels.base.MessageDeduper` 或自带的过期集合）。
2. 构造 `InboundMessage(channel=self.name, sender=<平台用户 id>, chat_id=<会话 id>, content=..., media=[本地路径], metadata={...})`。`metadata` 至少带 `message_id` / `external_message_id`（宿主用它在线程里去重），能确定时带 `chat_type`。
3. 交给 `ChannelIntake.submit()`；真正接收时：
   - `ctx.channel_hub.is_sender_allowed(channel=, chat_id=, sender_id=)` 为假就丢弃。未绑定的会话一律拒绝，可以把 `chat_id` / 用户 id 写进日志或 `status()`，方便用户复制去绑定。
   - `message = ctx.channel_hub.route_inbound(message)`：映射到绑定角色的会话，补上 `role_id`、`thread_id`、`session_key_override` 等元数据；`chat_type` 缺省时取渠道的 `default_chat_type`。
   - `metadata["conversation_duplicate"]` 为真时丢弃，否则 `await ctx.bus.publish_inbound(message)`。

约定：

- **chat_id 是渠道本地的会话标识**，也是用户在角色绑定里填的值，必须稳定、可从平台界面或状态信息里拿到。一个渠道有多种会话类型时用前缀区分，例如 QQBot 的 `c2c:<openid>` / `group:<openid>`、QQ（NapCat）群聊的 `gqq:<群号>`。
- **访问控制只在角色绑定上**，插件不要自己维护发送者白名单。私聊绑定的对方即会话本身；群聊绑定放行所有成员，只忽略黑名单（`blocked_senders`）里的发送者 id。`is_sender_allowed` 支持可选的 `sender_alias`（如 Telegram 用户名），黑名单条目可以写成别名、忽略大小写匹配。`/stop` 这类控制命令也应先过 `is_sender_allowed`。唯一刻意的例外是 `/chatid`（别名 `/myid`）：每个渠道插件在入站处理里自己识别它（`core.common.channel_chat_types.is_chat_id_command`），未绑定的会话也回复会话类型与绑定面板要填的号码（`chat_id_command_reply`，类型声明取自 `ctx.manifest.channel_chat_types(<渠道>)`），只有已绑定会话黑名单里的发送者（`channel_hub.is_sender_blocked`）不回复；它不进入角色对话。平台特有的群聊过滤（如 QQ 群必须 @ 机器人）仍由插件负责。
- **会话键**：绑定后的消息用角色会话 `role:<role_id>`（`route_inbound` 写进 `session_key_override`），未经路由时退回 `<channel>:<chat_id>`。出站处理和流式状态统一用 `infra.channels.session_key.resolve_outbound_session_key(msg, default_channel=self.name)` 计算，与 `TurnStarted` / `StreamDeltaReady` 的 `session_key` 对齐。`/stop` 这类控制命令用 `channel_hub.resolve_runtime_session_key(channel, chat_id)` 找到角色会话，再交给 `interrupt_controller.request_interrupt(...)`。
- 用户引用了一条历史消息时，用 `infra.channels.reply_context.build_inbound_text_with_reply_context()` 拼进正文，保持各渠道的格式一致。

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

- `subscribe_outbound` 接收 Agent 回合的最终回复（`OutboundMessage`）。发送成功或失败后调用 `ctx.channel_hub.mark_delivery(msg, default_channel=self.name, delivery_status="sent"|"failed", external_message_id=...)`，让会话里的消息状态正确。
- `register_channel` 让模型能用 `message_push` 主动发消息。`description` 会写进工具描述的「当前可用渠道」列表，用一句话说明渠道身份和 chat_id 格式；工具描述只列出当前已注册、未停用的渠道。
- `unregister_channel` 传入自己的 `text` 回调，只注销本实例的注册，不会误删换代后新连接的注册。

## 6. 可选钩子

核心不按渠道名写死策略，而是询问渠道对象的可选钩子，表格与默认值见 [渠道钩子](plugins-tutorial.md#渠道钩子runtime-api-23)。实践要点：

- `supports_stream_events(chat_id)`：只对真能实时展示的会话返回 `True`（Telegram 和 QQBot 只开私聊）。返回 `True` 就必须消费流式事件，见下一节。
- `system_prompt_hint(chat_id)`：只写渲染限制和渠道身份这类硬规则（例如 Telegram 禁止 Markdown 表格、QQBot 提醒主动推送用 `channel=qqbot`），保持简短，它每轮都会进系统提示词。
- `default_chat_type`：只支持私聊的渠道写 `"private"`，入站没带 `chat_type` 时由路由补上。
- `uses_bot_commands = True`：只有在 `start` 里读取 `ctx.bot_commands`（如注册 Telegram 命令菜单）的渠道才声明；宿主会把命令列表并入复用键，其它插件增减命令时它才会重连。
- `status()`：返回 `{"connected": bool, "account": str, "detail": str}`（后两项可省略），`channels.list` 原样带给桌面端。适合放机器人名称、断线原因、最近一个被拒绝的未绑定会话。`status()` 抛错时渠道显示为 `failed`。

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

- **配置与 setup**：用 `shiori_plugin_testkit.packages.stage_plugin_package` 把包暂存到临时目录，交给 `PluginKernel([root], services=HostServices(event_bus=EventBus(), plugin_configs={...}))`，断言无凭据时 `kernel.channels == []`、有凭据时贡献了一个同名渠道、`${ENV}` 占位符算未配置、`model_json_schema()` 的字段名能渲染成密码框（参考 `plugins/telegram/tests/test_plugin.py`）。
- **渠道行为**：平台 REST 用 `httpx.MockTransport` 替代，长连接用假连接；`ChannelContext` 直接构造，`channel_hub`、`push_tool` 可用简单替身（参考 `plugins/feishu/tests/conftest.py`）。至少覆盖：未绑定会话被拒绝、入站去重、`pause_intake` 期间缓冲、`stop` 对未启动实例安全、流式收尾与失败回退。
- **真实运行时**：testkit 的 `plugin_runtime` fixture 启动隔离的 `AppRuntime` 和桌面服务，可用于验证设置保存、热换代。
- `pyproject.toml` 声明 `test = ["shiori-plugin-testkit==0.1.0"]` extra 和 pytest 配置（`-W error`、`asyncio_mode = "auto"`），`TESTING.md` 写明仓库外运行方式和真机验收清单。

仓库内运行 `uv run pytest plugins/<id>/tests`；合并前用隔离环境验收：

```sh
uv run python scripts/verify_plugin_tests.py --plugins <id>
```

它从副本构建非 editable wheel、在干净 venv 里跑插件测试并审计模块来源，细节见 [插件测试](../agents/plugin-testing.md)。

## 10. 检查清单

- [ ] manifest 声明 `channels` 能力和渠道，渠道名与插件 id 一致且今后不改。
- [ ] 凭据不全时 `setup` 直接 return；凭据字段名能触发密码框；`${ENV}` 占位符按未配置处理。
- [ ] 构造函数不产生流量；`configuration_key` 覆盖全部连接设置。
- [ ] `start`/`stop` 可重复调用；`stop` 先断来源再排空任务；出站和推送注册在 `stop` 里撤销。
- [ ] 入站经 `is_sender_allowed` → `route_inbound` → 去重 → `publish_inbound`；用 `ChannelIntake` 处理换代暂停。
- [ ] 开了流式就消费事件并在最终回复时收尾；失败时退回普通发送。
- [ ] `register_channel(..., description=)` 写清 chat_id 格式。
- [ ] 测试离线，`verify_plugin_tests.py --plugins <id>` 通过。
