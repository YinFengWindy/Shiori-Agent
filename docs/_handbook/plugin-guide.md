# 插件指南

插件包在 `plugins/<id>/`：`manifest.yaml`、`backend/`、可选的 `ui/`、`surface/`、`background/` 和 `tests/`。本篇写行为语义；方法签名以 [API 参考](plugin-api.md) 为准，那份文件由 `python -m scripts.gen_plugin_api` 从源码生成。另外两篇专题：

- [生命周期与准入](plugin-lifecycle.md)：规划顺序、只登记的插件、预执行闸门、重载、启停、诊断和信任。
- [前端契约](plugin-frontend.md)：renderer 入口、对等依赖、注入的 `client` 与 `host`、后台模块和 surface。

版本记录见 [插件变更](plugin-changelog.md)。手把手的写法见 [插件开发](plugins-tutorial.md)。这些文档与源码冲突时以源码为准。

## manifest

### 字段

UTF-8 YAML。字段在 `apps/backend/agent/plugin_host/manifest.py` 解析；外部包（工作区目录或 ZIP）另由 `package_contract.validate_package` 检查，未知顶层字段一律拒绝。

| 字段 | 必填 | 值 |
| --- | --- | --- |
| `api` | 是 | 整数 `4`。`api: 2`、`"4"`、`4.0`、`5`、缺失都是 `unsupported_api`，并且最先检查 |
| `sdk` | 是 | 最低 SDK 约束，语法见下节。缺失或写错是 `invalid_manifest` |
| `id` | 外部包必填 | `[a-z][a-z0-9_-]{0,63}`；内置包省略时取目录名 |
| `version` | 外部包必填 | 完整 SemVer 2.0 |
| `entry` | 外部包必填 | 包内 `.py` 后端入口；内置包默认 `backend/plugin.py` |
| `inject` / `optional_inject` / `provides` | 否 | 服务 Key 名，见[服务 Key](#服务-key)。同一个名字不能同时在 `inject` 和 `optional_inject`；任何以 `host.` 开头的名字都拒绝 |
| `contributes.channels` | 否 | 静态渠道声明；非空时 `inject` 必须含 `channels`。规则见[渠道插件](channel-plugins.md) |
| `frontend.entry` | 否 | 包内前端入口文件（`ui/index.tsx` 这类）。P7 之前宿主仍按目录发现 `ui` / `background` / `surface` |
| `renderer` | 否 | 预编译的 `ui` / `background` / `surface` 入口，**临时保留到 P7**，见[前端契约](plugin-frontend.md#入口与产物) |
| `peer_dependencies` | 声明 `renderer` 时必填 | `react` 与 `react-dom` 的范围，随 `renderer` 保留到 P7 |
| `assets` | 否 | 必须存在的包内常规文件列表，默认 `[]` |
| `dependencies` / `optional_dependencies` | 否 | 插件 ID 列表（强 / 可选），不能重复出现在两边 |
| `supports_hot_unload` | 否 | 布尔，默认 `true`；`false` 的插件只能随重启变化 |
| `display_name` / `category` / `default_enabled` | 否 | 标题、`feature` / `channel` / `system` 分组、默认启用（严格布尔） |
| `distribution` | 否 | `builtin`（默认）或 `external` |
| `desc` / `author` / `config_model` | 否 | 描述与配置模型 |

已删除：`runtime_api`、`capabilities`、`package_contract`、顶层 `channels` 按名字拒绝（「api: 4 不再接受 …」）；`host_dependencies` 在外部包里是未知字段。`api` 先于 `sdk` 检查，所以 `api: 2` 且缺 `sdk` 报的是 `unsupported_api`。

### `sdk` 与 `peer_dependencies` 的比较语法

两者用同一套小语法（`agent/plugin_host/versions.py`）：空格分隔的 `=`、`>`、`>=`、`<`、`<=` 比较，逻辑与；不带运算符的 SemVer 表示相等。例如 `>=4.0.0`、`>=4.0.0 <5.0.0`。**不支持** caret（`^`）、tilde（`~`）、通配、逗号、`||` 和连字符范围，`4` 这种不完整版本也不行。build 元数据不参与比较。宿主是预发布版本时，必须有一条比较项写的是同一 `主.次.补丁` 的预发布版本才算满足。

`sdk` 写错语法：安装和发现都是 `invalid_manifest`。语法对但不包含当前 SDK：安装被拒（`incompatible_sdk`），已装的包和内置包在名册里是 `BLOCKED` / `incompatible_sdk`，不中断启动。`peer_dependencies` 写错语法是 `invalid_version_range`，宿主的 React 不满足是 `incompatible_runtime`，缺少 `react` 或 `react-dom` 是 `missing_dependency`。

## setup 上下文

后端入口必须有顶层 `async def setup(ctx)`。`ctx` 是 `shiori_sdk.runtime.PluginRuntimeContext`（宿主实现在 `apps/backend/agent/plugin_host/runtime_context.py`）：

| 成员 | 作用 |
| --- | --- |
| `plugin_id`、`plugin_dir` | 插件 ID 和包目录 |
| `require(KEY)` / `get(KEY)` / `provide(KEY, impl)` | 取 `inject` 声明的服务 / 取 `optional_inject` 声明的服务（没有提供方时为 None）/ 发布 `provides` 声明的服务 |
| `on` / `watch` / `emit` | 加入事件链、旁观最终事件、发出事件，见[事件](#事件) |
| `effect(label, dispose)` | 登记卸载时的清理；`dispose` 可同步可异步 |
| `expose(api)` | 把本插件的 Python 接口交给同一代里声明了依赖它的插件（对方用 `DEPENDENCIES` 取） |

上下文上**没有** `spawn`、`on_drain`、`log`、`config`、`data_dir`。它们都是服务：

- 后台任务：`ctx.require(BACKGROUND).spawn(coro, name=...)`；需要保留调用方运行租约直到任务结束的用 `spawn_runtime`。卸载时取消，不排空。
- 重载前的排空：`ctx.require(RUNTIME).on_drain(callback)`；`RUNTIME.was_active` 为 `True` 表示这个插件在本次 setup 之前已经在运行：代内重载重新拉起的实例、可选依赖的提供方代内启停时随之重新 setup 的实例都是这样，换代时上一代处于 `ACTIVE` 的插件也是这样；首次启动和从停用状态启用时为 `False`。用它跳过只该做一次的启动恢复。语义见[生命周期](plugin-lifecycle.md#代内重载)。
- 配置：`ctx.require(CONFIG)`；私有数据目录与迁移：`STORAGE`；工作区目录：`WORKSPACE`。
- 日志：用标准库 `logging`。

这些 Key 都在 `shiori_sdk.core.services`，必须先写进 manifest 的 `inject` / `optional_inject`。

`effect` 的顺序：卸载时先停掉事件订阅和任务，再按登记的逆序跑其它清理；单项失败也继续清理；开始清理后不再接受新登记。

## 服务 Key

`ctx.require` 只取 `inject` 里的 Key，`ctx.get` 只取 `optional_inject`，`ctx.provide` 只发布 `provides`；没声明就抛内核的 `undeclared_key`。声明了但当前没有提供方时，`require` 抛 `provider_unavailable`。消费方每次用时再取，不要缓存跨代的引用。

宿主在任何插件启动前 `provide` 它拥有的核心 Key。`config`、`kv`、`dependencies`、`runtime`、`services`、`storage` 是逐插件现建的：宿主在内核里只放一个标记，`require` 时换成为这个插件建好的对象；`kv`、`services` 只在被声明时才建。宿主没能建出某个已声明的对象时抛 `HostServiceUnavailable`，setup 失败并留下 `PluginDiagnostic`。账号、渠道、工具等 Key 给每个插件一份按插件 ID 隔离的视图。

插件 `provides` 一个核心 Key 会让整代启动失败；两个插件 `provides` 同一个 Key 时双方都 `BLOCKED`。细节见[生命周期](plugin-lifecycle.md#规划)。

`EVENTS` 是领域事件总线（`on` / `off` / `emit`），和下面的内核事件不是一回事。

### P6a / P6s 的新 Key

这些是新 Key，没有加在已有 Protocol 上。契约放在 `shiori_sdk.core`，因为核心或别的插件要消费，不能从插件包导入。

| 名字 | Key | 谁提供 |
| --- | --- | --- |
| `reply_policy` | `REPLY_POLICY` | 系统插件 `natural_chat`。只有提示和选用。多条消息的协议和发送留在核心 |
| `scene` | `SCENE` | 系统插件 `scene`。`request` 返回释放函数，调用方交给 `ctx.effect` |
| `scene_host` | `SCENE_HOST` | 宿主。`followup_wanted` 读主动策略，不是 `Roles` 上的新方法 |
| `affection` | `AFFECTION` | 系统插件 `affection`。状态文件仍是 `roles/<id>/state/affection.json` |
| `affection_host` | `AFFECTION_HOST` | 宿主事实：角色、会话、在场、记忆文档、对话模型 |
| `mcp_tools` | `MCP_TOOLS` | 宿主。动态 MCP 工具的登记。管理工具仍走 `TOOLS.register` |
| `schedule_host` | `SCHEDULE_HOST` | 宿主（P6s）。按角色跑定时回合（`run_turn`）或直接投递（`deliver`），走当前发布代；端口本身跨代 |
| `scheduler` | `SCHEDULER` | 系统插件 `schedule`（P6s）。只有创建、列出、取消角色的任务。消费方用 `optional_inject`，`get` 为 `None` 时不用定时能力。任务仍在 `<workspace>/schedules.json` |

旧的 `scene_observations` Key 在 4.0.0 删除。NovelAI 改为 `optional_inject: [scene]`，`get(SCENE)` 为空时不登记需求。场景插件经 `SCENE_HOST.on_published` 开始观察：本代已发布时（代内重载、代内启用）立即开始，否则等宿主发布本代。`mcp` 是外部插件，新装默认关闭，没启用时没有 `mcp_add`；`mcp_servers.json` 里已有服务器的老工作区会在启动时一次性写入 `[plugins.mcp] enabled = true`（见[生命周期](plugin-lifecycle.md)）。

即时聊天的选用：插件在提供，并且角色 `runtime_config.natural_chat_enabled` 是布尔 `True`。插件关闭时不选用，回复是单条。`natural_chat_enabled` 仍在角色 JSON，不进 `config.toml`。

## 事件

事件是 frozen dataclass，顶层字段不能是 list、dict、set（用 tuple、frozenset 或只读 mapping）；否则 `emit` 抛 `TypeError`，`watch` 在登记时就拒绝。

`emit(event)` 的顺序固定：

1. **`on` 链**：按插件顺序（依赖深度，再按插件 ID；同一插件内按登记先后），不按时间。每个处理器返回同类型的事件（可以是 `dataclasses.replace` 出来的替换品）或 `Veto`。返回 `Veto` 立即结束，后面的处理器、核心检查和 watcher 都不跑。返回别的东西，或替换品违反上面的字段规则，都算该处理器出错。
2. **核心检查**：宿主用 `Kernel.check` 登记的固定检查，作用在链的最终事件上，任何插件都改不掉，所有插件停用时也照样生效（例如 `ToolCalling` 的外部上下文工具限制和最小 shell 护栏、`ReasoningFinished` 的引用标记清理）。检查也可以返回 `Veto`。
3. **watcher**：拿到最终事件，每个插件、每种事件一个串行队列，`emit` 不等它们。队列积压到 256 条后新的丢弃并记警告。被否决的事件不会到 watcher。

处理器出错时看事件类型的 `on_error`：

- `fail_open`（默认）：记日志，事件原样传给下一个处理器。
- `fail_closed`：链停止，`emit` 返回 `Veto("插件 <id> 处理 <事件> 失败: …")`。目前只有 `ToolCalling` 是 `fail_closed`：护栏出错时这次工具调用被拒，记为 `denied`。

目前的核心检查：

- **`ToolCalling`**（`agent/tools/execution.py`）：外部上下文的工具限制（见下文），以及最小 shell 护栏（`agent/tools/shell/guard.py`）。护栏只拒绝三类：整个删除或移走文件系统根、盘符根、用户主目录、工作区根（或其下全部内容）；写块设备（`dd of=`、重定向、对设备 `mkfs`）；格式化磁盘（`Format-Volume`、`Clear-Disk`、`format X:`）。会拆开 `;`、`&&`、管道等，并进入 `sh -c`、`pwsh -Command`、`cmd /c`（最多两层）。交互命令拒绝和 rm→mv 改写仍归 shell_safety / shell_restore 插件。
- **`ReasoningFinished`**（`agent/core/citation.py`）：记忆引用归核心，任何记忆引擎（或没有）都一样。链之前，核心读每条消息末尾的 `§cited:[...]§` 标记（没有时用 `recall_memory` 返回的 ID）记为 `cited_memory_ids` 并去掉标记；链之后的检查去掉没人消费的末尾协议标签（`<name:value>`）和行内 `[§id]` 引用，包括插件写回的。其它位置残留的标记在投递时去掉。标记格式在 `shiori_sdk.memory.engine`（`CITED_MARKER_PATTERN` 等）。

`Veto` 在哪些事件上能停下回合，写在各事件的 docstring 里（`shiori_sdk.core.conversation`、`shiori_sdk.core.tools`）。代内重载时，内核会等正在执行的 `on` / `watch` 处理器跑完；旧实例释放后、新实例 setup 前，这个插件的处理器暂时不存在，事件照常由其它插件和核心检查处理。

## 宿主服务的约定

- **外部上下文的工具**：群聊、陌生私聊里，发送者不是已绑定用户的回合只能用登记时声明了 `ctx.require(TOOLS).register(tool, ..., external_allowed=True)` 的工具。默认不声明。受限的工具不进模型的工具列表和 `tool_search` 结果，`tool_search` 也解锁不了，硬调会得到「只有它的用户能要求」的工具结果。声明在每次检查时从注册表读，回合中途登记的未声明工具同样受限。MCP 工具不能声明（会抛错）。已绑定用户本人的消息不受限，在群里也一样。
- **渠道头像**（`AVATARS`）：`refresh(kind, channel, id, fetch)`，`kind` 是 `"sender"` 或 `"chat"`。没有缓存或上次尝试超过 7 天才算到期；到期时立刻记下尝试时间，在后台调 `fetch()` 并返回任务，否则返回 None。图片限 PNG / JPEG / GIF / WebP、最多 1 MiB，宿主缩成小 PNG 单独存。`fetch` 失败或图片被拒只记警告，不影响收发，已有头像保留。未知 `kind` 或空的渠道 / ID 抛 `ValueError`；插件作用域释放后调用抛 `RuntimeError`，未完成的任务被取消。在宿主收下消息（`route_account_inbound`）之后再调。
- **外部回合**（`EXTERNAL_TURNS`）：非渠道来源（如直播弹幕）用 `submit(...)` 请角色回应。按群聊语义走角色的外部线程 `thread:<role>:<platform>:<conversation_id>`，发送者永远不是绑定用户，只能用外部可用的工具。角色忙时立即返回 `busy`，不建线程、不写消息；拿到角色闸门后跑完为止。不经渠道入站队列，也不派发出站，回复由插件自己呈现；桌面和渠道的打断到不了它，取消 `submit` 才会取消它。`platform` 不能是 `desktop` 或正在运行的渠道名。
- **可发现服务**（`SERVICES`）：`register(service_id, contract=, label=, methods={...}, metadata=)` 发布只活在本实例生命期内的异步 JSON 方法，renderer 用 `client.services` 发现和调用，见[前端契约](plugin-frontend.md#注入的-client)。
- **账号发送回执**：`account.send` 通常返回平台真实的 `message_id`；平台明确接收但不给消息 ID 时返回 `accepted: true`（只有布尔 `true` 允许空 ID），不能用任务运行 ID 冒充。确认送达的私聊可以附带 `conversation: {channel, chat_id, chat_type: "private"}`（`shiori_sdk.accounts.routing.AccountRoute`），必须是插件解析出的规范入站地址，不能从目标 ID 猜。宿主按账号平台校验渠道；地址无效时记日志并省略，不重试已经发生的发送。
- **命令**（`COMMANDS`）：`register(name, handler, description=...)`，把返回的移除函数交给 `ctx.effect`。名字已被占用、或不是不含 `/`、`@`、空白的小写，抛 `ValueError`，setup 失败。命令处理器不算 `on` 处理器，重载时不等它。

- **外部回合的结果**：`ExternalTurnResult.status` 是 `replied`（带 `reply` 文本）、`busy` 或 `duplicate`。
- **后台结果回报**（`BACKGROUND_RESULTS`）：只能在已认证的角色工具回合里 `capture()`，得到的目标保留原角色、线程、实际渠道和绑定发送者，插件不能另选。`report(result_id, text)` 在角色闸门内重新校验后经角色正常出站路径回报；同一个 ID 只回报一次（含失败不明的情况），返回 `False` 表示已经试过。只在进程内，不跨重启恢复。
- **进程资源**（`PROCESS_RESOURCES`）：`acquire(key, factory)` 按插件私有、带版本的 key（如 `tasks-v1`）取同一进程内的资源。工厂只能构造空闲对象，不得持有代际上下文、提供方、RPC 或任务。候选代际只挂接、不激活；发布后激活新挂接并关闭被移除的资源，回滚只关闭无主的临时资源，退出时全部关闭。不持久化，重启后不重建。
- **HTTP 上限**：`HttpGet.get` 和 `ChannelHttp.request` 接受 `max_response_bytes`。非负上限同时检查 `Content-Length` 和流式解码后的字节（含重定向），超限时关闭响应、不重试，抛 `shiori_sdk.http.ResponseTooLarge`（带 `max_response_bytes`）。不传时行为不变；testing 里的 HTTP fake 实现同样的约定。
- **`message_push`**：插件经 `TOOLS` 拿到的 `message_push` 失败时抛异常（未知渠道、不支持的载荷、发送失败、角色未绑定的目标），正常返回就表示已发送或已随当前回合排队，不要再解析返回文本。角色只能经它发到自己的桌面会话；发往渠道用 `account_send`。宿主专用的 `push_proactive=False` 把文字 / 图片记为补充内容，不标为主动消息；它必须是严格布尔，只来自宿主的执行上下文，模型参数和工具 schema 里都没有；`False` 时带 `file` 直接拒绝。`account_send` 的同名参数（配 `push_chat_id`）语义相同。

### 渠道与账号

渠道插件的写法见[渠道插件](channel-plugins.md)，这里只列宿主侧的约定：

- **附件工具**：宿主为每个回合建一份不可变的 `ToolAttachmentScope(channel, paths)`（本回合收到和明确引用的附件），放在工具执行上下文的 `TOOL_ATTACHMENT_SCOPE_KEY` 下。消费方要用 `Tool.context_precedence` 保护这个键、缺失时拒绝，并自己执行渠道与文件策略。
- **只读改投地址** `account.resolve`：收到 `account_id` 和 `AccountTarget.to_payload()`，返回 `AccountRoute.to_payload()`（规范 `channel`、`chat_id`、`chat_type`、可选正整数 `message_thread_id`），不发送任何东西，也不扩大平台权限。自然主动改投必须有它，缺了会明确失败，宿主不猜平台地址。普通 `account.send` 不调用它。
- **工具授权**：账号声明 `full_tools` 能力时才显示「完整工具」开关（`AccountResponseRules.allow_full_tools`，缺省 `false`）。授权只对 `accounts.report(tool_conversation=AccountRoute(...))` 报告的当前私聊地址生效；不报告就不授权，地址变了旧的排队消息和后台目标都失去授权。插件放进入站 metadata 的 `account_full_tools` 会被渠道中心丢掉。
- **固定对端**：账号报告 `fixed_peer` 能力表示连接本身决定准入，桌面隐藏私聊 / 群聊开关和发送者黑名单，`full_tools` 仍单独控制。提供方要在登记前归一化旧的准入规则，拒绝不支持的修改；这个能力不绕过宿主的准入和授权检查。
- **分条回复**：`ChannelsCapability.subscribe_outbound(..., supports_reply_sequence=True)` 让普通渠道回合可以按条发送。每条发完后渠道在 `OutboundMessage.delivery_outcome` 写 `DeliveryOutcome(status, external_message_id)`；入队不是送达回执，`uncertain` 不能自动重发。失败或不明时停止这一批，不重试。
- **打断**：`InterruptController.request_interrupt` 要带接收渠道、chat、`account_id`、`chat_type` 和 `message_thread_id`；只给 session 或部分地址时不会推断账号 / 话题的回合。
- **入站 ID**：`TurnCommitted.external_message_id` 带原始入站消息 ID（非渠道回合为空），角色决定不回复时渠道也能据此完成持久化的入站处理。

### 托管环境

`shiori_sdk.managed` 给需要私有运行环境的插件（如语音）提供固定产物下载、原子安装、自有进程和后台操作；`register_runtime_rpc` 登记一组 `runtime.*` RPC，前端用 SDK 的 `ManagedRuntimePanel` / `useManagedRuntime`。模型、安装内容和编排策略归提供方。目前只支持 Windows x64。

- **两个根**：状态根（`current.json`、`location.json`、锁、日志、提供方文件）与 `install_root`（下载、`s/` 暂存、`v/` 版本、子进程临时 / 缓存和提供方声明的 `scratch` 目录）分开。位置跨代保留，`OwnedService.root` 仍是状态根。
- **`runtime.relocate {directory?}`**（`ManagedRuntime.relocate` / `Installation.relocate`）：在已存在的本地盘目录里建一个专用子目录作安装根；不带 `directory` 恢复默认。只有什么都没装、没保留、没有任务时才行；UNC / 设备路径和已有安装条目的目标被拒，Windows 上按不区分大小写比较。位置记录读不出来时报在 `error` 里，可以在没有指针时直接重设位置，或者删除环境来修复。
- **`runtime.remove`**（`ManagedRuntime.remove`）：要求没有运行中的服务、没有任务；没装过也能执行。先删指针，再删安装根里的安装条目；链接 / junction 只解除、不跟进；自选的安装根删空后一并删除；状态根里的文件都保留。阶段是 `removing`。
- **空闲空间检查**：复制前检查安装卷：缺的产物字节 + 安装后大小，再加 `max(1 GiB, 5%)` 余量；不够就以「磁盘空间不足」失败。原地导入单个文件不计下载副本。
- **`runtime.prepare {source}`**：`source` 是用户选的原始绝对路径文件（不能是链接 / junction），可以是全部产物的 ZIP，或 `import_asset` 指定的单个产物；校验后缀、单产物的精确大小和 SHA-256 后才构建。原文件从不复制、移动或删除，ZIP 成员解压到暂存区。构建回调是 `build(staging, resources)`。成功后清掉下载缓存和其它版本；失败或取消保留缓存；清理失败只写进 `error`，不撤销发布。
- **状态**：除阶段与进度外，含 `reclaimable`（可回收的下载字节）、`staging`、`location`、`customized`、`required`、`required_import`、`free`、`removable`、`relocatable`。
- 托管服务在插件释放时停止，不在 `on_drain` 里停。

### 角色数据

- **好感度**：`AffectionSummary` 只由好感插件的 `history`、`chat_status` RPC 返回，`RoleRecord` 与会话 metadata 不带它；第一次对话初始化之前为 `null`。`value` 是 -100 到 100，七个阶段：「厌恶」-100～-50、「冷淡」-49～-1、「陌生」0～19、「熟悉」20～39、「朋友」40～59、「亲密」60～79、「挚爱」80～100；`progress` 是当前阶段内的 0～1。`floor` 是达到过的最高「熟悉」及以上阶段的起点（20 / 40 / 60 / 80），从没达到「熟悉」时为 `null`；好感不会再低于它。「陌生」的角色可以掉到负值，但衰减不会让好感变成负数。消费方要处理全部七个阶段。寂寞增长和关系主动动机要求好感至少 60（「亲密」起点）。
- **关系状态**：关系快照是好感插件的私有数据（`relationship_snapshot.json`），SDK 不再导出它的类型；聊天侧栏要的关系标签由 `chat_status` 返回。需要亲近程度的用好感。

## 版本

SDK 独立 semver，源只在 `packages/sdk/python/shiori_sdk/_version.py`。大版本是破坏性变更。4.x 内禁止给已有 Key 或 Protocol 加方法；新能力用新 Key 或新 Event。下一个大版本可以合并拆开的 Key，不要把 `SESSIONS_PRESENCE_V2` 这种名字一直留着。

npm 包、宿主 `setup.py` 和 host-testing 的精确 pin 必须等于这个版本。`node scripts/check_sdk_release.mjs --align` 只核对这三处。正式 tag 再跑完整检查：`plugin-changelog.md` 要有当前版本的 `## X.Y.Z` 条目，拒绝回退，也拒绝已发布 tag 上的同版本源码被改掉。没有 Unreleased 批次，也没有 `sync_sdk_version.mjs`。

插件自己的 `version` 独立。SDK 升大版本不因此给每个插件升 patch。插件的 `shiori-sdk` 依赖要承认它实际要跑的 SDK；本仓库插件是 `>=4.0.0,<5`。

## 4.0 基线里的插座

回滚在 `SESSIONS`：`last_passive_turn`、`rollback_last_turn`。记忆引擎的 `rollback_turn` 在 `MEMORY_ENGINE` 上。

在场心跳在 `SESSIONS.presence`：`record_user_message`、`last_user_at`、`record_initiated_sent`、`last_initiated_at`。表列仍是 `last_user_at` / `last_proactive_at`。`role:` 会话用原 key，其他会话在有 `metadata.role_id` 时记到 `role:<id>`；这条映射和 `proactive_v2` 共用 `SessionStore.presence_key`。

角色命名空间在 `ROLES.plugin_settings(role_id, namespace)`。目前只有 `proactive`，其它名字抛 `KeyError`。宿主仍用核心的主动配置解析它，直到主动行为移出核心。写入和桌面保存角色一样会清空已退役的 `candidates`（#427），插件读出再写回不会把旧绑定带回来。渲染侧的 `roleSettings` 槽已经存在，不是这次新加的。

`CONVERSATION.deliver_initiated_reply(session_key, reply, source)` 和事件 `InitiatedMessageCommitted` 在契约里，现在还没有提供方：声明 `inject: [conversation]` 的插件会因缺少提供方而 `BLOCKED`。4.x 不能事后再给这个 Protocol 加方法，所以签名先放进 4.0。

**4.0 发版门闩**：带 SDK 4.0 的桌面版本发出之前，宿主必须提供 `CONVERSATION`（`deliver_initiated_reply` 与 `InitiatedMessageCommitted`）。

## 测试

插件测试只用 `shiori_sdk.testing`。`FakePluginContext` 把内核调用交给真正的 `Kernel`，服务用 testing 里的 stub；`require` / `get` 只认 manifest 里声明的名字，和宿主一样抛 `undeclared_key`。`KernelHarness` 是同一套内核的显式入口，`await harness.idle()` 等 watcher 处理完。不要导入 `tests.support`、`shiori_host_testing` 或 `apps/backend`。

testing 没有按 #904 原计划删掉约 2.7k 行，保留的模块现在是真内核 harness 加服务 stub（维护者确认的偏离）：

- 保留：被插件测试直接或经由装配好的上下文使用的 stub。`channel_group`、`channel_intake`、`resources` 没有插件直接导入，但分别经 `FakeChannelSetupContext.fake_channels.group(...)`（grok_bot、telegram）、`fake_channel_context` 的默认 `intake_factory`（telegram）和 `FakeServiceContext` 提供的 `RESOURCES`（browser_use、computer_use、meme）在用，所以保留。`scene_observations` 随旧 Key 一起删除。
- 移走：`bridge`（桌面 bridge 请求 helper）只有宿主集成测试用，已移到 `shiori_host_testing.bridge`。
- `shiori_sdk.testing` 的模块顶层不能导入会拉进 `httpx` 的模块（例如 `shiori_sdk.core.services`），插件测试环境不一定装了它。

仓库外的验收是 `python -m scripts.verify_plugin_tests`：用 SDK wheel 和插件 wheel 安装，不把宿主放进 `sys.path`。CI 的 `plugin-isolation` 跑的就是它。前端测试工具见[前端契约](plugin-frontend.md#测试入口)。

## 还留在 SDK 里的东西

内核、`shiori_sdk.core` 的 Key / Protocol / Event、testing（真内核 + stub），以及插件仍在导入的 helper：渠道、文件、进程、记忆类型、账号、消息、SQL、命令和提示词。P4 删掉的是 `ctx` 上的 capability 属性；这些模块现在就是插座契约和测试 stub，不是第二套 capability 镜像。
