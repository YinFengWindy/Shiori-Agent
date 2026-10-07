# 插件开发

Shiori 只有一套显式 v2 插件运行时。插件提供 `manifest.yaml` 和异步 `setup(ctx)`，宿主按声明授予能力，并用作用域回收事件、阶段贡献、工具和后台任务。

## 包布局与发现

```text
plugins/example/
  manifest.yaml
  backend/
    plugin.py
    config.py
  ui/index.tsx         # 可选，主窗口贡献
  background/index.ts # 可选，app.background
  surface/index.tsx   # 可选，桌面 surface
  tests/test_plugin.py
  pyproject.toml
  TESTING.md
  README.md
```

后端扫描 `bootstrap.paths.plugin_roots()` 返回的内置插件根目录，以及工作区的 `plugins/`。开发态和桌面 bundle 的内置包位于安装资源的顶层 `plugins/`；wheel 安装态使用已安装插件包。内置包保留显式 `api: 2` 协议，默认入口为 `backend/plugin.py`，入口作为包导入，内部可使用相对 import。

工作区 `plugins/<目录>/manifest.yaml` 声明的外部包必须通过 [Package Contract v1](plugin-runtime-contract.md) 静态检查；合法包显示为 `UNTRUSTED`，在用户于设置 › 插件中经「信任…」（或 ZIP 安装/更新时的「信任并安装」「信任并更新」）确认并重启应用之前，不导入它的后端或 renderer；内容一变授信即失效（流程见[运行时契约](plugin-runtime-contract.md#main-window-ui-loader-213)）。配置 `enabled = true` 不代表信任。无效 manifest、入口和依赖显示为 `BLOCKED`；只有旧 `kv.json`、没有 manifest 的目录被忽略，数据不会因此删除。

按 manifest ID 检测全部候选：同 ID 的所有包均为 `CONFLICT`，不选择内置或工作区优先者；同目录名但不同 ID 的包分别显示。插件管理保留各候选的版本、来源、实际目录和结构化诊断，拒绝切换未通过准入的候选。目录级代码新增、替换、删除后重启应用；配置保存或启停插件产生的新运行代沿用本次应用启动的候选、manifest 和准入快照，应用重启后才重新扫描。各运行代的导入命名空间、句柄和 effect 仍独立。

```yaml
api: 2
id: example
version: '0.1.0'
desc: 示例插件
capabilities:
  - config
  - events
  - lifecycle
  - rpc
config_model: config:ExampleConfig
supports_hot_unload: true
```

`capabilities` 必须显式列出，可以是空列表。只声明实际使用的能力；未授权属性访问会抛 `CapabilityNotGranted`。声明了能力而宿主缺少其背后的服务（如 workspace、role_store、session_manager、http）时，宿主在调用 `setup` 前抛 `HostServiceUnavailable` 并指明缺失的服务名，插件不需要也不应再对这些属性做 `is None` 判断。`config_model` 可以是入口中的类名，也可以是相对入口包的 `模块:类名`。模型必须继承 Pydantic `BaseModel`。

`display_name` 是设置 › 插件里显示的名称（省略时显示 ID）。可选的 `category` 决定插件在列表中的分组：`feature`（功能）、`channel`（渠道）、`system`（系统组件，默认折叠，用于宿主内部护栏、诊断命令这类用户不需要日常操作的插件）。省略时声明了 `channels` capability 的插件归入渠道，其余归入功能；`system` 只能显式声明。取值不在这三者之内时 manifest 被拒绝。Package Contract v1 的外部包自 Runtime API 3.1.2（#678）起也接受 `display_name` 与 `category`（含 `system`），校验规则相同；更早的宿主把它们当未知字段拒绝。

可选的 `default_enabled`（严格布尔值，省略为 `true`）决定 `[plugins.<id>]` 没有显式 `enabled` 时插件是否启用；显式的 `enabled` 始终优先，设置 › 插件的开关写的就是显式值。目前 `browser_use`、`computer_use`、`novelai`、`gpt_sovits_tts`、`sensevoice_asr` 声明为 `false`，新安装默认停用。把已有内置插件改为 `false` 时必须同时把 ID 追加到 `agent/plugin_default_enabled_migration.py` 的 `DEFAULT_DISABLED_PLUGINS` 和 `config.example.toml` 的 `[_migrations] plugin_default_disabled` 回执：升级用户的旧配置在首次启动时被显式写成 `enabled = true`，保持升级前的状态；模板带回执，新安装不受迁移影响（`test_manifest.py` 会校验 manifest 与迁移清单一致）。成为内置插件时就默认停用、从未被缺省启用过的插件（`gpt_sovits_tts`、`sensevoice_asr`）不登记。Package Contract v1 的外部包自 Runtime API 3.1.2 起也接受 `default_enabled`。

## setup 与配置

```python
# backend/config.py
from pydantic import BaseModel

class ExampleConfig(BaseModel):
    """Values editable through the plugin configuration channel."""
    label: str = "example"
```

```python
# backend/plugin.py
from shiori_sdk.lifecycle import AfterTurnCtx
from .config import ExampleConfig

async def setup(ctx):
    """Registers this activation's contributions and cleanup."""
    config = ExampleConfig.model_validate(ctx.config.as_dict())

    async def after_turn(event: AfterTurnCtx):
        await ctx.rpc.emit("updated", {"label": config.label})

    async def read_label(payload):
        return {"label": config.label}

    ctx.events.on(AfterTurnCtx, after_turn)
    ctx.rpc.register("label.get", read_label)
```

自动表单按 JSON Schema 渲染：字段标签取 Pydantic `Field(title=...)`，说明取 `description`（不写 `title` 时 Pydantic 会生成 "Timeout Seconds" 这类英文标题，请为每个字段写中文 `title`）；数字字段可用 `json_schema_extra={"unit": "秒"}` 声明单位，`ge`/`le` 会作为取值范围；`list[str]` 渲染为可增删的标签列表；`SecretStr` 或名称含 secret/token/password/api_key 的字符串按密钥遮挡；对象、对象列表等其余形状放进「高级」折叠区，以 JSON 编辑。

运行配置来自 `[plugins.example]`。`enabled` 是宿主拥有的启停字段，不应放进插件模型。插件自己在 `setup` 校验读取值；宿主配置 schema 注册表为 `plugin.config.get/set` 提供 schema、默认值和写入校验。没有配置模型的插件不会得到自动表单。配置值可以写成 `${NAME}` 引用环境变量（整值为引用时也可来自 `workspace/memory/<NAME>` 文件）：插件运行时拿到展开后的值；`plugin.config.get` 返回未展开的原值，并用 `env_status` 标出每个含引用的字段当前是否可解析（`set` / `unset`）；`plugin.config.set` 对含引用的值按展开后的值校验、按原引用落盘，密钥不会以明文写回 config.toml。

桌面普通设置草稿不携带插件配置快照。保存时后端在同一配置事务锁内保留当前插件表，因此不会覆盖其它窗口刚完成的插件设置或启停更改。原始 `runtime.apply` 仍是整份配置替换；普通表单通过 `preserve_plugins: true` 明确选择保留语义。

## 能力与副作用

| 能力 | 用途 |
| --- | --- |
| `events` | `ctx.events.on(EventType, handler)`；卸载先停用并退订，再清理其它 effect，与登记先后无关 |
| `lifecycle` | `ctx.lifecycle.contribute(phase, modules)`；登记阶段模块 |
| `tools` / `tool_hooks` | 注册工具或工具执行前处理器 |
| `proactive_gates` | 贡献主动行为准入 gate |
| `channels` / `bot_commands` | 贡献 manifest 已声明的渠道（见[渠道声明](#渠道声明)）及机器人命令 |
| `accounts` | `ctx.accounts.register/register_saved/report/...`：向宿主登记通信账号及其归属，随插件作用域释放（见[渠道插件](channel-plugins.md)） |
| `services` | `ctx.services.register(service_id, contract=, label=, methods=)`：发布可被 renderer 按契约发现、调用的 JSON 服务方法（Runtime API 3.1.1，如语音 `shiori.asr.v1` / `shiori.tts.v1`，见[运行时契约](plugin-runtime-contract.md#runtime-api-311-plugin-services-native-resources-and-background-chat)） |
| `avatars` | `ctx.avatars.refresh(kind, channel, id, fetch)`：到期时在后台用插件的下载把发送者或群的平台头像交给宿主缓存，`fetch` 返回 None 即记为无头像；卸载取消在途获取（见[渠道插件](channel-plugins.md)） |
| `rpc` | 注册 `plugin.<id>.<method>`，发送同命名空间事件 |
| `background` | `spawn` 管理作用域任务；`spawn_runtime` 另保留当前 runtime lease，卸载取消并等待任务 |
| `kv` | 工作区 `plugin-data/<id>/kv.json` 中的私有状态 |
| `config` | 本代插件配置快照 |
| `dependencies` | 读取已声明提供方的本代公开 API |
| `runtime` | 本代是否重载、前代是否活动，以及收尾任务登记 |
| `workspace` / `roles` / `sessions` | 工作区、角色快照/素材、会话元数据/素材替换；不导出完整存储聚合 |
| `scene_observations` / `models` | 场景观察需求与按角色持有的 chat/vision 模型快照 |
| `http` / `resources` / `processes` / `tool_turn` | 注入 HTTP、资源路径、MCP/进程所有权和当前工具回合 |

外部上下文（群聊、陌生私聊）里，发送者不是已绑定用户的回合只能使用声明过外部可用的工具：`ctx.tools.register(tool, ..., external_allowed=True)`。默认不声明，即这类回合看不到、也调不动该工具；已绑定用户本人的消息不受限。只给陌生人触发也安全的工具声明，例如 NovelAI 的 `generate_image`。MCP 工具不能声明。规则见[运行时契约](plugin-runtime-contract.md#tools-in-external-contexts-489)。

能力名的完整权威清单是 SDK 的 `shiori_sdk.runtime.KNOWN_CAPABILITIES`（宿主 `agent/plugin_host/manifest.py` 与 SDK 测试替身共用 `parse_capabilities` 校验）。不要自己构造另一份 RoleStore 来写同一份角色文件，应获取宿主共享的 `roles` 窄接口。渠道使用 `ChannelPluginContext` 的账号、渠道和头像等协议；桌宠使用 `ServicePluginContext` 的角色、存储、工具和 RPC 协议，renderer 通过 SDK surface 能力声明交互。能力是架构边界，不是 Python 进程内安全沙箱。

其它外部资源用 `ctx.effect("label", disposer)` 登记清理；disposer 可同步或异步。Python 插件作用域分两段处置：先停止接收新事件并撤销所有 `ctx.events.on` 订阅，再按登记的逆序（LIFO）清理其余 effect，包括自定义 disposer、后台任务与贡献。订阅和资源的登记先后不影响退订优先规则；其它资源之间仍需按依赖顺序登记，例如先登记 writer，再登记需要向 writer 最终 flush 的采集器，使采集器先清理。

开始处置后拒绝新订阅、后台任务和资源登记；即使总线已选中某个 handler，只要它尚未开始也不会再调用。已经执行中的 handler 不会被强制取消，插件应在 disposer 中取消或等待其持有的任务。`ctx.events.off` 使用原始 handler 的对象身份退订，移除同一 handler 的重复订阅，重复退订安全。一项清理失败不会跳过剩余 effect。初始化抛错使用相同规则撤销已登记贡献；再次启用使用新作用域，不能重复保留旧订阅。

## 渠道声明

所有外部聊天渠道都是插件，宿主只拥有 `desktop`。从零写一个渠道插件（配置表单、渠道契约、入站路由、流式、测试）的完整步骤见 [写一个渠道插件](channel-plugins.md)；本节只列声明与钩子的规则。

贡献外部聊天渠道的插件要在 manifest 里静态声明渠道，并同时声明 `channels` 能力（Runtime API 2.2）：

```yaml
capabilities: [channels, accounts, kv, rpc]
channels:
  - name: qqbot                      # 必填，渠道名
    label: QQBot                     # 必填，显示名
    chat_types:                      # 必填，渠道支持的会话类型
      - type: private                # private / group
        label: 私聊
        chat_id_label: 用户 OpenID    # 会话标识的标签
        chat_id_hint: 对方的用户 OpenID # 可选
        prefix: 'c2c:'               # 可选，拼在号码前组成存储的 chat_id
```

- 渠道名是会话线程和消息引用的数据键，发布后不要改名。账号 ID 采用 `<插件 id>:<平台账号>`；渠道名必须是小写标识（`[a-z][a-z0-9_-]{0,63}`），`desktop` 由宿主保留。
- 声明是静态的：插件停用、未信任或还没有账号时，桌面端也能经 `channels.list` 列出这个渠道。账号插件应始终贡献渠道，并从插件自己的存储恢复账号；凭据缺失只影响对应账号的连接状态。
- `chat_types` 必填（Runtime API 2.5），声明渠道的会话类型（`private` / `group`，各带标签、号码标签与提示、可选内部前缀），缺失时宿主拒绝 manifest。渠道插件用它标注会话类型，并为 `/chatid` 等命令生成可识别的会话标识。
- 渠道项还可选 `contact_label`（群聊黑名单里成员 ID 的说明）、`group_listening: true`（Runtime API 2.13，支持群聊旁听）和 `instance_prefix`（必须以 `<name>_` 开头，如 Telegram 的 `telegram_`）：按账号拆出的连接可用 `<instance_prefix><后缀>` 作渠道名，沿用该项的会话类型，`channels.list` 为启用且 `ACTIVE` 的插件每个实例列一行。
- `ctx.channels.add(channel)` 只接受本 manifest 声明过的 `channel.name`、声明的 `instance_prefix` 下的名字，或带非空 `account_id` 的 `<声明名>:<后缀>` 账号实例，否则 setup 失败，插件回滚为 `FAILED`，诊断码 `undeclared_channel`。
- 两个插件声明同一个渠道名（或一方的 `instance_prefix` 与另一方的渠道名、前缀相互覆盖）时，两者都是 `CONFLICT`（诊断码 `duplicate_channel`），都不会激活。
- 渠道的启停和换代由宿主的 ChannelHost 管理，不要用 `background` 自己起连接任务。跨代复用连接时，渠道提供 `configuration_key`，它变化就重建连接；声明了 `uses_bot_commands = True` 的渠道，宿主还会连同 bot 命令列表一起比较。
- 渠道可以实现可选的 `status()`，返回 `{"connected": bool, "account": str, "detail": str}`（`account`、`detail` 可省略），`channels.list` 会原样带给桌面端。

### 渠道钩子（Runtime API 2.3）

核心不按渠道名写死策略，而是向渠道对象询问下面几个可选钩子；不实现就取中性默认值。协议定义在 `shiori_sdk.channels`：

| 钩子 | 作用 | 不实现时 |
| --- | --- | --- |
| `supports_stream_events(chat_id) -> bool` | 这个会话是否接收 `StreamDeltaReady` 流式事件，用于实时预览 | 不发流式事件，只收到最终回复 |
| `system_prompt_hint(chat_id) -> str` | 追加在系统提示词末尾（空一行）的渠道规则，例如渲染限制 | 不追加 |
| `default_chat_type: str`（类属性） | 入站消息没带 `chat_type` 时由路由补上的值 | `"unknown"` |
| `uses_bot_commands: bool`（类属性） | 渠道在 start 时读取 `ctx.bot_commands`（如 Telegram 的命令菜单）；命令列表变化时宿主会重建它 | `False`，命令变化不重建连接 |

```python
class QQBotChannel:
    name = "qqbot"

    def supports_stream_events(self, chat_id: str) -> bool:
        return chat_id.startswith("c2c:")  # 群聊只收最终回复

    def system_prompt_hint(self, chat_id: str) -> str:
        return "## 官方 QQBot 渠道规则（硬性）\n- 发送消息时使用 `channel=qqbot`。"

    async def start(self, ctx):
        ctx.push_tool.register_channel(
            self.name,
            text=self.send,
            description="官方 QQBot，私聊 chat_id 格式为 c2c:<user_openid>",
        )
```

- 钩子按渠道名查询当前已发布的连接；换代中正在排空的旧连接仍按它自己的钩子回答。
- 开了流式事件就要订阅 `StreamDeltaReady` 并自己节流，最终回复仍经出站消息送达。
- `register_channel(..., description=...)` 的说明写进 `message_push` 工具描述的「当前可用渠道」列表，用来告诉模型渠道身份和 chat_id 格式。工具描述只列出当前已注册、未停用的渠道。
- 用到这些钩子或 `description` 参数的包要声明 `runtime_api: ">=3.0.0 <4.0.0"`；旧宿主会忽略钩子，并拒绝未知的 `description` 参数。

## 阶段与依赖

阶段槽位为 `before_turn`、`before_reasoning`、`prompt_render`、`before_step`、`after_step`、`after_reasoning`、`after_turn`（SDK 的 `shiori_sdk.lifecycle.PHASE_SLOTS`；向其它名称 `contribute` 会抛 `ValueError`）。模块按 `shiori_sdk.lifecycle.LifecycleModule` 协议声明唯一 `slot`、所需 `requires` 和导出的 `produces`（无依赖或无导出时写空元组）；宿主核心拥有具体执行顺序与帧语义。用到 `AfterTurnCtx`、`PHASE_SLOTS`、`require_phase_slot` 或按该协议声明 `requires` / `produces` 的外部包声明 `runtime_api: ">=3.1.0 <4.0.0"`。

```python
from shiori_sdk.lifecycle import PromptRenderCtx
from shiori_sdk.prompting import PromptSectionRender

class ExamplePrompt:
    """Adds a prompt section after the host creates its prompt context."""
    slot = "example.prompt"
    requires = ("prompt_render.emit", "prompt:ctx")
    produces = ("prompt:ctx",)

    async def run(self, frame):
        ctx = frame.slots.get("prompt:ctx")
        if isinstance(ctx, PromptRenderCtx):
            ctx.system_sections_bottom.append(
                PromptSectionRender(name="example", content="Example context", is_static=True)
            )
        return frame

async def setup(ctx):
    """Contributes one scoped prompt module."""
    ctx.lifecycle.contribute("prompt_render", [ExamplePrompt()])
```

模块依赖其它插件提供的槽位时，还应在 manifest 声明插件依赖。例如 meme 的 `dependencies: [citation]` 保证 citation 先活动；提供方缺失、停用或失败时 meme 为 `BLOCKED`，不会显示活动但缺少提示词。卸载提供方会级联其强依赖消费者。

需要调用另一个插件的 API 时，提供方用 `ctx.expose(api)`，消费者声明 `dependencies` 和同名 capability，再调用 `ctx.dependencies.require("provider")`。只需要加载顺序时不必调用 `require`。可选提供方用 `optional_dependencies` 和 `get_optional`：它不会强制启动提供方，提供方不可用时返回 `None`，也不会触发消费者级联卸载。

## 热卸载与进程退出

`supports_hot_unload` 是严格布尔值，省略时为 `true`。不能可靠在进程内卸载的插件必须显式写 `false`。

- 正常卸载先检查目标和全部强依赖消费者；任一活动插件不支持热卸载，整次操作拒绝，所有实例保持活动。
- 当前设置修改采用整代准备/发布。如果当前代存在这类活动插件，插件启停、插件配置、普通或原始配置保存均返回 `plugin_restart_required`，包含 `plugin_ids`，不启动候选、不写配置或角色数据、不切换 generation。完全相同配置与只改角色模型绑定的事务仍可执行。
- 用户应退出应用后修改配置，再重新启动；本轮没有“已保存、待重启”的第二份配置。
- 真正退出宿主、未发布候选失败/取消/丢弃，以及初始化回滚都强制回收已登记资源。声明不会豁免 effect 清理。

内核的 `unload`、`terminate_all` 及宿主 `CoreRuntime.stop` 正常入口遵守声明；`force` 仅供最终资源回收路径。普通退出仍按引用排空，不因强制清理而提前取消已接受的工作。

## 桌面 RPC、事件与 UI

`ctx.rpc.register("label.get", handler)` 注册 `plugin.example.label.get`。前端插件组件得到已绑定自身命名空间的 `client.call("label.get")`，不自行拼宿主 IPC。`await ctx.rpc.emit("updated", payload)` 通过 `PluginBridgeEvent` 与所属 generation 的服务下发 `plugin.example.updated`，旧代事件不会冒充新代。

主窗口在构建时发现 `plugins/*/ui/index.tsx`，默认导出 `PluginUiModule`：

```tsx
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";

const exampleUi: PluginUiModule = {
  pluginId: "example",
  settingsSection: { kind: "schema", label: "Example" },
};
export default exampleUi;
```

`settings.section` 不再是设置侧栏的顶层条目：它注册为内建「插件」区块下的一个子页面。设置 › 插件的列表按 manifest 的 `category` 分成功能、渠道、系统组件三组，有设置页的插件在所在行显示「设置」按钮，点开进入它的设置页（页头带返回），不再作为「已安装」旁的子标签；侧栏始终只有模型/记忆/外观/高级/我的身份/插件/关于七项（「频道」已随渠道插件化移除，#363；「语音」已随语音业务迁入插件移除，#677）。深链 `openSettingsWorkspace("plugins", { subsectionId: pluginId })` 直接打开该插件的设置页。manifest 声明了 `config_model` 的插件无需手写 `ui/index.tsx` 就能自动获得一个 schema 表单设置页，页标题取自后端 `plugins.list` 的回退链：manifest 的 `display_name` → 插件记录名（未声明 `display_name` 时即插件目录名）→ `id`，所以请在 manifest 里写出 `display_name`。账号插件的凭据与响应规则在角色页编辑，保存在插件自己的账号存储，不放在自动配置表单里。只有需要自定义表单组件、或额外贡献 `navPage`/`roleAssets` 等插槽时才需要手写（如 novelai——它的手写 `settingsSection` 会优先于自动注册，不会重复出现两个子标签）。已使用的插槽还包括 `nav.page`（story、novelai）、`role.assets`（desktop_pet）、`account.detail`（四个渠道插件的账号详情）。角色设置（`roleSettings`，并入宿主角色保存）、自管角色面板（`roleUi`，Runtime API 3.1.1，经插件自己的 RPC 读写，如 gpt_sovits_tts）与聊天图片动作（`chatImageActions`）也有独立贡献契约。插件 UI 只通过注入的服务和 RPC 协作，启停状态决定其可见性。

Runtime API **2.4.0** 起，绑定的组件（`navPage` 及其侧栏、自定义 `settingsSection`、`roleAssets`、`accountDetail`）除了 `client` 还会收到 `host`（即宿主服务，内置插件也可以继续用 `usePluginHostServices()`）。其中三项是宿主的呈现：`host.feedback.error("加载失败", { detail, persona: true })` 把提示放进宿主唯一的提示队列；`<host.ui.InlineError persona message={error} actions={…} />` 是宿主的页面内报错块（`layout` 可选 `row` / `strip` / `card`）；`<host.ui.ConfirmDialog persona="destructive" … />` 是宿主的确认弹窗（参数与宿主自己的一致）。`persona` 默认 `false`；传 `true`（或 `"generic"`）让看板娘吟风用该处的通用台词出面（报错 / 警告带一句，成功 / 普通提示只露脸），传场景键（`not_configured` / `unauthorized` / `quota` / `network` / `upstream` / `destructive` / `discard` / `confirm`）用宿主为该场景写好的台词。台词永远由宿主写，插件只能选场景；用户在 设置 › 外观 关掉「看板娘」后，一律回到不带她的样式。用到 `host` 的包声明 `runtime_api: ">=3.0.0 <4.0.0"`。`host` 还提供 `config`、`assets`（2.10）、`pickFiles` / `pickFilePaths` / `pickDirectory`（后两者 3.1.5）、设置页角标 `host.ui.SettingsSavedStatus`（3.1.4）以及账号详情用的 `AccountStatusCard`、`AccountDetailActions`、`Reveal`。细节见[运行时契约](plugin-runtime-contract.md#runtime-api-24-host-feedback-and-inline-errors)，NovelAI 生图的失败卡片和报错提示就是这样接的。

`app.background` 在隐藏的 plugin-host renderer 运行，入口是 `background/index.ts` 的 `{ pluginId, setup(ctx) }`。桌宠已通过它拥有控制器、surface、托盘项与订阅。它的 `BackgroundCtx` 不是 Python 上下文：通过自己的 `effect`、`events`、`hostEvents`、`rpc`、`surfaces`、`tray`、`store`、`assets` 管理资源，用 `reportFailure` 把已处理但需要人看到的失败写进桌面诊断日志（2.11）；3.1.1 起还有作用域内的原生资源 `native`（录音、播放、全局快捷键）与 `chat`（为角色发起、取消回合）。使用 `surface/` 入口渲染独立桌面窗口。

Runtime API **2.1.0** 为 UI、surface 和后台注入同一套通信接口。新包使用这些接口时声明 `runtime_api: ">=3.0.0 <4.0.0"`。它们沿用 manifest 的 `dependencies` / `optional_dependencies`；不会建立另一套依赖注册表，也不会隐式启用提供方。

```ts
// UI / surface：自身后端、事件、后台都只传局部名称。
await client.call("label.get");
const off = await client.events.on("updated", (payload) => updateLabel(payload));
await client.background.call("sync", { forceVisible: false });
off();

// manifest: optional_dependencies: [desktop_pet]
const pet = await client.dependency("desktop_pet");
if (pet) await pet.background.call("sync", { forceVisible: false });
```

`dependency(id)` 对已声明但缺失、停用、失败的提供方返回 `null`；未声明时抛出 `plugin_dependency_undeclared`。拿到的 peer 同样提供 `call`、`events.on`、`background.call`，不会接受 `plugin.<id>.*` 全局名称。每次操作应重新取得当前注入 client 的 peer；旧代 peer 不会自动连接到新代。提供方在获取后停用时，调用以 `plugin_unavailable` 失败。只在用户操作或状态变化时重试，避免错误循环。

后台通过 `await ctx.rpc.handle("sync", async payload => ...)` 注册自身方法，UI/surface 的 `background.call` 等待其完成，处理失败原样保留稳定错误码与消息。方法只由后台注册，同名重复注册立即报错。请求最多并发 128 个，15 秒未响应以 `plugin_timeout` 失败；等待 renderer 不占用后端 RPC 的调度容量，后台可在处理方法里继续 `await ctx.rpc.call(...)`。

后台 `await ctx.events.on("action", handler)` 只订阅自身插件事件；其它插件事件必须通过 `await ctx.rpc.dependency(id)` 取得 peer。宿主事件使用独立的 `ctx.hostEvents.on("chat.done", handler)`，该入口拒绝 `plugin.*` 名称。Python 后端继续通过 `ctx.dependencies.require/get_optional` 访问插件经 `ctx.expose` 导出的 API；声明、停用与卸载规则不变。

注入 client 由挂载的 UI/surface 或后台作用域持有。React 订阅 effect 把 `client` 放入依赖数组，并返回 `events.on` 给出的 disposer；异步订阅完成前若组件已经卸载，立即调用该 disposer。宿主会在卸载、挂载失败、后台 setup 失败、窗口退出、主文档刷新/导航以及运行代际替换时统一回收订阅、方法注册和待返回请求。同页导航与子 frame 导航不会回收主文档的通信。真实配置发布或 bridge 重连会替换注入 client，并重建后台作用域；`runtime.applied.changed` 只表示实际发布新代，同代幂等重试、无变化保存与仅改角色模型绑定的事件为 `changed: false`，不会打断现有请求；返回旧代结果的重试不再发布事件。RPC 响应仍保留原操作的结果。渲染入口就绪或失败通过 `plugins.changed` 刷新名单：仍处于 ACTIVE 的插件保留通信 client 和后台作用域，失败插件仍回收自己的 UI、后台和 surface。后台已有业务工作若跨卸载仍在执行，仍应由插件的 effect 取消或等待，旧 handler 不得回复到新代。

`ctx.rpc.emit` 返回是否已经交给连接的桌面传输，不能解释成每个 renderer 都已消费。桌宠工具据此保留 `desktop_bridge_unavailable`，未投递的动作不占用冷却或本轮次数。桌宠动作、隐藏、包切换已走通用通道，宿主不再有桌宠动作事件或 `desktop:pet-sync`。回复气泡属于桌宠；屏幕感知插件独立。宿主自 Runtime API 3.1.1（#677）起不再有语音业务：识别与合成由 `sensevoice_asr`、`gpt_sovits_tts` 以 `services` 发布 `shiori.asr.v1` / `shiori.tts.v1`，桌宠拥有语音偏好、输入手势与播放编排，宿主只提供通用原生录音、播放与按键资源。

这些 API 是可表达、可观测的协作契约，不是安全隔离。同 realm 的受信插件仍有宿主权限；CSP 没有放宽。

## 测试、安装与数据升级

测试放在本包 `tests/`，文件与 `backend/` 模块对应。通过显式安装的 `shiori-sdk[testing]` 使用公共 fake 与包暂存：

```python
from pathlib import Path
from shiori_sdk.testing.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[1]
# 在 tmp_path 下整包暂存，保留源码/manifest/资源，排除运行状态和构建缓存。
# staged = stage_plugin_package(PLUGIN_DIR, tmp_path / "plugins/example")
```

SDK 的 `sdk_context` fixture 从测试文件向上（不越过 pytest rootdir）找到本包 `manifest.yaml`，只授予其 `capabilities` 声明的能力（未知能力名与宿主一样报错）；访问未声明的能力抛 `CapabilityNotGranted`，与宿主一致。manifest 只用于读取，`plugin_dir` 是隔离的临时目录；包内文件按包资源读取，不要写入 `plugin_dir`。测试不在包内时，在 `conftest.py` 覆盖 `sdk_plugin_dir` fixture。

兄弟插件通过 `plugin_directory("citation")` 定位，并在 `pyproject.toml` 明确声明安装依赖；不得推导原仓库路径，也不得导入宿主测试树。异步测试由 pytest-asyncio 执行，公共支持来自 SDK 的 pytest entry point；独立插件测试不安装宿主。真实 AppRuntime 集成 fixture 由宿主开发包 `shiori-host-testing` 提供，仅在显式安装该包时通过其 pytest entry point 注册。

仓库开发使用 `uv sync --dev`，再 `uv run pytest plugins/example/tests`。仓库外验收运行 `uv run python -m scripts.verify_plugin_tests --plugins example --output <仓库外新目录>`：从副本构建非 editable wheel，在独立环境运行真实插件测试，检查模块来源，并确认 await 后故意失败的异步断言真正执行。完整步骤见 [插件测试](../agents/plugin-testing.md) 与各包 `TESTING.md`。

旧停用标记仅由配置启动升级读取：按当前 manifest 身份写入缺失的 `[plugins.<id>].enabled = false`，显式配置优先。持久化失败保留原配置与标记，重试不会覆盖已保存选择；无法确认当前插件身份时保留标记，等待包可用。内核日常启停不读取标记。已归核心的主动/场景偏好保持各自升级逻辑。

通用 KV 位于 `agent/plugin_host/kv.py`，旧 `.kv.json` 的现存可恢复数据仍由 `plugin_data` 原子迁入工作区。旧 `workspace/plugins/<id>/kv.json` 优先于包内 `.kv.json`，统一原子迁入 `workspace/plugin-data/<id>/`。历史 `plugin_config.json` 迁移复用宿主静态 discovery，只为通过准入的内置 owner 处理数据；`CONFLICT`、`UNTRUSTED`、`BLOCKED` 保留来源且不导入。旧 workspace 中已有 manifest 的包不能作为其它 ID 的配置来源；没有 manifest 的旧数据目录按 ID 迁移。目录别名必须唯一且不与其它 ID 相撞；旧后端代码目录只按唯一包目录名归属。主 TOML 已提交的迁移凭证会独立补齐 workspace 完成标记，即使准入随后变更，也不会重读、导入或删除旧来源。有效来源从旧 workspace、当前包或旧 `apps/backend/plugins/<id>` 归档到该数据目录，并在持久化启动时一次性升级为主配置的 `[plugins.<id>]`；已有 v2 配置整表优先，仅含旧宿主 `enabled` 的表保留开关并导入参数。成功标记独立保存在数据目录，之后编辑、删键或删除整表都不会重新读取旧 JSON。旧源只在落盘成功后删除，未选中的候选保留；写入失败保留旧源并中止启动。default_memory 的 `config.local.toml` 同样迁入各自数据目录，加载和初始化共用路径解析，默认值来自代码，运行时不向安装包写入。升级前已被安装器删除的数据无法恢复。

记忆插件通过 SDK 注入的 `MemoryStorage` 解析配置与迁移私有数据；宿主实现继续复用 `plugin_data` / `data_migration` 的原子迁移与凭证。所有插件通过声明的 SDK 协议使用宿主能力。历史独立数据在 owner 打开存储之前迁移。默认 memory2 与 observe 数据库分别位于 `plugin-data/default_memory/memory2.db`、`plugin-data/observe/observe.db`。显式 `db_path` 保持不变；引擎、初始化、向量兼容性检查和管理脚本使用相同的 owning resolver。旧库仍被进程内 owner 使用时拒绝迁移并要求重启，避免准备新运行时代际时截断旧库的后续提交。

SQLite 用 backup API 复制包含已提交 WAL 的一致快照，不能只复制 `.db` 主文件。目标发布前保存内容凭证；未确认的已有目标报冲突并保留双方。完成凭证位于 `private_runtime/plugin-data-migrations/<id>/`，独立于可删除的插件目录，因此清理插件数据后不会从旧位置复活状态。旧来源通常保留为升级备份，运行时不再向旧来源写入；确认备份和引用后可人工归档。桌宠旧 pet 子目录是例外：验证新素材并提交全部新引用后，由 owner 删除旧 pet 文件以维持包删除语义，不影响其他角色素材。不要删除迁移凭证来“修复”空数据。

`default_memory/recall_inspector.jsonl` 和 observe 的 `.last_cleanup` 各归自己的插件数据根，不能整目录迁走旧 `observe/`。meme 私有旧图库迁到 `plugin-data/meme/library/`；共享 `common_emojis.json` 与角色素材仍属宿主，宿主初始化器不再预建插件图库或 observe 目录。

NovelAI 生成记录、原始请求、输出图和提示词库存于 `plugin-data/novelai/generation/`；参考图在保存时复制到其中的 `references/`，共享 imports 仅作导入来源，不能被插件整目录删除。Story 数据库位于 `plugin-data/story/stories/`，每个故事采用的 CG 复制到该故事目录的 `assets/`。会话在持久化本地图片时复制到 `sessions/media/` 并保留原始来源；旧消息在打开会话库时以同一事务迁移引用。清理 NovelAI 的私有数据不删除已经成为故事或会话内容的副本。重新生成仍需 NovelAI 的原始生成记录和请求；清掉这些记录后，会话图片可查看，但不再具备重新生成来源。完整工作区备份同时保留 `sessions.db`、`sessions/media/` 与使用中的插件数据目录。


External package authors: see [External Plugin Runtime Contract v1](plugin-runtime-contract.md)
for the versioned distribution layout, compatibility gate, ESM/CSS requirements
and independent build example. The tutorial's bundled source-plugin workflow
continues to use the existing v2 path.

角色级的桌宠状态与 NovelAI 自动 CG 偏好采用 `roles/roles.json` 顶层的 `plugin_data.desktop_pet`、`plugin_data.novelai` 不透明命名空间，插件拥有 schema，宿主只协调角色字段与插件草稿的单次原子提交。清单 v5 在角色投影前完成旧字段捕获与移除，即使插件停用也不会因普通角色保存丢失数据；已有命名空间优先。桌宠最终素材单独归 `plugin-data/desktop_pet/pets-<role_id>/`，旧路径在素材副本完成后再原子改写。插件重新启用会清理已删角色、无效包记录及孤儿 pet 文件；清空素材后的同名包可以重新导入。

因此，仅备份 `plugin-data/<id>/` 不代表完整插件备份：还须保留主配置的对应插件表、对应角色命名空间和 `private_runtime/plugin-data-migrations/<id>/` 凭证；角色命名空间恢复时按角色合并，保留其他插件和角色字段。普通「同时删除插件数据」只清理私有目录与主配置插件表，保留角色命名空间、迁移凭证和设备偏好。清理 NovelAI 数据保留 Story 和会话各自持有的图片副本；清理 Story 自身数据会同时删除其故事及 CG。重新安装仍需对插件代码重新授权，授权后该插件可继续读取保留的角色偏好。

Story 播放偏好保留为设备 renderer 的 `localStorage["shiori.story-preferences.v1"]`；桌宠位置/窗口状态保留在 Electron `userData/plugin-data/desktop_pet.json`。它们不随工作区迁移或清理，复制设备体验时另行备份。shell_restore 的新默认是工作区内受保护的 `recovery/shell_restore/`，保存的是用户原文件，不能随普通插件数据删除。显式 `AKASIC_RESTORE_DIR` 保持原值；旧 `~/restore` 不自动归属任何工作区，也不移动或删除，须独立备份和恢复。


## 统一 SDK 3.0

新插件前端使用 `@yinfengwindy/shiori-sdk`，后端契约使用 `shiori_sdk`，并声明
`runtime_api: ">=3.0.0 <4.0.0"`。SDK 主文档位于
[packages/sdk/README.md](../../packages/sdk/README.md)，包括 wheel/tarball 构建、
公开协议和 `shiori-sdk[testing]` 的无宿主测试入口。
全部 22 个内置插件，包括四个外部渠道、桌宠和两个语音 provider，均使用 SDK 契约及 `shiori-sdk[testing]` 独立测试支持。
宿主导入守护没有迁移豁免，仓库外验证只安装目标及其显式依赖，不安装宿主。
真实 AppRuntime、渠道、窗口和进程集成由宿主测试及 `shiori-host-testing` 验证；
SDK 只定义公开协议和独立 fake，宿主保留服务实现。
