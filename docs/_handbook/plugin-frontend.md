# 插件前端契约

[插件指南](plugin-guide.md)的专题篇：插件 UI、后台模块和 surface 与宿主之间的 TypeScript 契约。类型的唯一来源是 `@yinfengwindy/shiori-sdk`（源码 `packages/sdk/src/`，契约类型在 `src/contract/`）；运行时导出清单是 `apps/desktop/src/plugins/uiContract.ts` 的 `pluginUiPeerExports`。生成的 [API 参考](plugin-api.md) 只覆盖 Python。与源码冲突时以源码为准。

前端统一使用 `frontend.entry` 单入口和具名导出。旧 `renderer` 与顶层 `peer_dependencies` 字段已删除。

## 入口与产物

单 frontend 入口写 `frontend: { entry: frontend.ts }`，入口显式导出 `ui`、`background`、`surface` 中需要的贡献；可以直接从原有模块 re-export。贡献对象本身沿用各自 SDK 类型，合并模块类型为 `PluginFrontendModule`。不要在模块顶层启动后台任务、打开窗口或申请原生资源：三个环境都可能求值同一个入口，只有各自宿主会挂载对应导出。

外部构建自动生成 `renderer/frontend.mjs`（名称只是产物路径，不是旧 manifest 字段），并将 manifest 改写为 `frontend: { entry, exports, css, peers }`。`exports` 来自构建器的真实导出表；CSS 自动收集。React 与 SDK 仍保持 external，共享宿主实例，源码 `package.json` 的 `peerDependencies` 由构建器写入 `frontend.peers`，安装前校验 React、React DOM 和 Shiori SDK 的范围。安装后每个声明的导出都会检查，加载失败仍按原激活令牌回滚整插件。一个包只获取一份受信资源快照，各窗口从同一个 ESM 选择自己的导出。

`node scripts/build-plugin.mjs --plugin plugins/<id> --output artifacts/plugins` 从声明的源码入口编译 ESM 和 CSS 并打 ZIP（要求 `api: 4` 与 `distribution: external`）。内置构建只读取 builtin 插件的 manifest，一份清单供各执行环境使用，不按目录或 kind 另找入口。外部源码不会进入宿主构建图。

产物是浏览器 ESM，必须含声明的具名导出；CommonJS、TypeScript/JSX 源码和缺少的导出会被拒绝。静态格式检查不执行插件代码；renderer 在激活时校验完整模块及贡献对象，失败回滚整插件。

| 具名导出 | 类型 |
| --- | --- |
| `ui` | `PluginUiModule`：设置、导航、角色等 UI 插槽 |
| `background` | `PluginBackgroundContribution`：`{ pluginId, setup(ctx) }` |
| `surface` | `PluginSurfaceModule`：`{ pluginId, surface: { component } }` |

`pluginId` 必须等于 manifest 的 ID。声明已退役的 `roleMemory`（宿主自己渲染记忆页，记忆插件只提供 `roles.memory.*` RPC）或 `roleUi`（改用 `roleSettings` 卡片，私有设置放 `storage: "plugin"` 的对话框里用 `usePrivateAutosave`）的 UI 模块校验失败。代码不能依赖 Vite glob、宿主源码相对导入或宿主重新构建。

`roleAffection` 挂在角色详情，`chatAffection` 挂在聊天状态栏。宿主只在该插件启用且登记了组件时挂载，两者都注入 `client` 与 `host`。props 只有定位标识：`roleAffection` 是 `{roleId, bridgeReady}`，`chatAffection` 是 `{roleId}`，宿主按角色给 `chatAffection` 加 key，换角色即重新挂载。槽里显示的数据都由插件自己取：好感插件用 `client.call("history" | "chat_status" | "stage_prompts_get" | "stage_prompts_set")`，在 `host.onEvent` 收到本角色的 `session.updated`（宿主在回合、主动消息、渠道回合存下后广播它，好感记账在此之前完成）或插件自己发的 `affection.chat_status.changed`（寂寞心跳、关系快照刷新之后）时重新读取 `chat_status`，不从宿主页面导入，宿主也不读、不转发这些数据。

`roleTasks` 挂在聊天右栏的「任务」面板，宿主只在该插件启用且登记了组件时挂载，注入 `client` 与 `host`。props 是 `{roleId, view, onViewChange}`（`PluginRoleTasksComponentProps`）：`view` 为空时组件作为任务列表的一组，排在宿主的后台任务、记忆维护之前；`onViewChange(非空值)` 后宿主把整个面板交给组件，组件按自己定义的 `view` 画详情、表单等视图，自带头部，返回时 `onViewChange("")`。宿主只保存 `view`、不解读它，面板按角色加 key，换角色即清空。组件在两种位置之间移动时会重新挂载。计划任务插件经 `client.call("list" | "create" | "update" | "cancel")` 读写，在 `host.onEvent` 收到本角色的 `schedule.tasks.changed` 时重新读取。面板外观用 SDK 的 `chatSidebarPanelClass`、`chatSidebarHeaderClass`、`chatSidebarScrollableClass` 与 `DetailRow`；列表里的组头、计数和任务行用 `roleTaskGroupHeadClass`、`roleTaskGroupCountClass`、`roleTaskRowClass`、`roleTaskRowTitleClass`、`roleTaskRowSummaryClass`，与宿主自己的任务组一致。

## 对等依赖与 import map

React、React DOM 和 SDK 主入口是宿主提供的对等依赖，不打进插件包。预编译时把 `react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@yinfengwindy/shiori-sdk` 设为 external，其它浏览器库自己打包。import map 把这些名字解析到包着**宿主自己实例**的 wrapper，所以 hooks、context 和 `instanceof` 与内置插件完全一致。

- 宿主当前保证 React / React DOM `19.2.0`（`agent.plugin_host.frontend_contract` 的固定 peer 版本）；`frontend.peers` 用[指南里的比较语法](plugin-guide.md#sdk-与-frontendpeers-的比较语法)写范围。
- SDK 主入口能导入的运行时名字只有 `pluginUiPeerExports` 里列出的那些；纯类型导出没有运行时存在。给这张表加名字是契约变更。
- `@yinfengwindy/shiori-sdk/testing` 只用于开发测试，`/contract` 是给主进程和 preload 用的纯类型入口，`/host-internal` 只给宿主；三者都不在 import map 里，插件运行时代码不能导入。
- 插件不得附带或要求安装私有的 npm / Python 运行时依赖。CSS 由插件自带并限定在自己的类名下；共享类名（`cardClass` 等）是 Tailwind 工具串，已在宿主样式表里。

## 资源授权与加载

只有唯一、已启用、`ACTIVE` 的工作区候选拿到资源授权。主进程的 `plugins.list` 回复里带授权后的入口与 CSS URL（`shiori-plugin:` 协议），资源处理器再核对路径和宿主记住的启动时文件哈希，只提供 `.mjs`、`.js`、`.css`、常见图片和字体；新增或改动的脚本、样式、资源一律拒绝。CSP 只放行这个协议和 import map 的哈希，生产环境不加 `unsafe-inline` 脚本或 `unsafe-eval`。替换插件代码后要重启应用。

名册初载、桥接重连、`runtime.applied`、`plugins.changed`、`plugins.reloaded` 和启停开关走同一条串行刷新路径。某个入口导入、样式或导出校验失败时，宿主撤掉这个插件已渲染的部分，在插件管理页显示 `UI FAILED`，并经 `plugins.activation.report` 回报后端，后端把整个插件回滚到 `FAILED` / `RESTART_REQUIRED` 并重新发布名册，其它窗口随之拆掉过期的贡献；其它插件不受影响。

每个入口（和名册行）带一个不透明的 `activation_token`，插件每次激活成功都会为当前实例铸新的。renderer 回报激活结果时原样带回，不匹配就当作未知插件处理。这样停用再启用之后，旧代际里被放弃的加载不能确认或判失败当前实例。代内重载后，被重载插件的 renderer 入口用新 token 重新回报激活。

## 注入的 client

UI 组件、surface 和后台模块都收到注入的 `client`（`PluginRpcClient`）：

- `client.call(name, payload, { timeoutMs })`：调本插件后端的 RPC。
- `client.events.on(name, handler)`：订阅本插件的事件，返回取消函数。
- `client.dependency(pluginId)`：拿到 manifest `dependencies` / `optional_dependencies` 里声明过的同伴，用同样的本地名调用；可选同伴缺失或未激活时返回 `null`。
- `client.background.call(name, payload)`：调本插件后台模块用 `ctx.rpc.handle` 登记的方法。
- `client.services.list(contract)` / `client.services.call({plugin_id, service_id}, method, payload)`：按契约发现并调用其它插件用 `SERVICES` 发布的服务。不需要静态依赖，也不授予对方私有 RPC 的访问权；提供方或调用方已退役报 `plugin_service_unavailable`，方法未发布报 `plugin_service_method_unavailable`，不会悄悄换成别的提供方。

局部方法和事件名在 wire 上统一为 `<pluginId>.<name>`，不接受旧 `plugin.<id>.*` 别名。宿主 `plugin.config.*`、`plugins.*` 和其他宿主顶层命名空间不能作为插件 ID。已退役的本地 client 调用报 `plugin_unavailable`；重载时的本地在途调用报 `plugin_reloading`（“插件正在重载”）。这些本地失效错误的 `details.reason` 区分 `context_disposed`、`plugin_disabled`、`bridge_exited`、`runtime_replaced` 和 `plugin_reloading`，首次失效原因不被后续 dispose 覆盖，迟到结果不会交给新实例。后端 RPC 与后台通信还校验 `open` 登记的 owner：即使局部重载保留 generation，已经排队或迟到的旧 owner 请求也会在执行前以 `plugin_invalid_owner` 拒绝，不修改新实例或抢占其后台方法；`close` 和文档断开的清理保持幂等。

组件在注入的 `client` 变化时要重建订阅：真正的运行时发布或桥接重启会替换全部上下文，`plugins.reloaded` 只替换点名的插件，payload 的 `disabled_plugin_ids` 标明其中已经停用的插件；`runtime.applied` 的 `changed: false` 刷新和 `plugins.changed` 不替换仍然 `ACTIVE` 的插件的上下文。后台的 `hostEvents` 不接收带 `pluginGeneration` 的插件事件；插件事件走 `events` 或依赖 client。

宿主的贡献绑定按同一实例代次重挂插件子树：包括设置、导航、角色卡、图片动作和 surface 的错误边界；宿主持有的角色草稿不随之清空。同代码重载复用已求值模块和 CSS，只重建插件实例与后台 scope；无变化保存和无关插件重载保留原实例。新配置失败后若已按旧配置重新创建实例，后端在失败响应之前发布完整替换闭包，让已撤销 owner 的贡献重新取得上下文；部分恢复失败的插件随实际名册卸载，保存错误仍然显示。drain 拒绝或替换前要求重启时不提前宣布重挂成功。

## host 服务

绑定的组件（`navPage` 及其侧栏、自定义 `settingsSection`、`roleAssets`、`accountDetail`）除了 `client` 还收到 `host` prop（`PluginHostServices`）；内置插件也可以在组件树深处用 `usePluginHostServices()` 读同一个对象。完整成员以 `PluginHostServices` / `PluginHostUi` 类型为准：

- `host.feedback.{success,info,warning,error}(message, { detail?, action?, persona?, personaQuiet? })`：放进宿主唯一的提示队列，与宿主共用排队、时长、去重和离线过滤。
- `host.ui`：`InlineError`（页面内报错块）、`ConfirmDialog`（宿主确认弹窗）、`SettingsSavedStatus`（设置页角上的「正在保存…」/「已保存」，只在设置页里渲染）、账号详情用的 `AccountStatusCard`、`AccountDetailActions`、`Reveal`。
- `host.config`：本插件自己的配置。`get()` 读当前值（填好 schema 默认值，`${NAME}` 引用原样返回）；`save(patch)` 合并到顶层后走与设置页相同的校验和热应用，同一插件的保存逐个执行，被 schema 拒绝时报 `PluginBridgeError("plugin_config_invalid")` 且什么都不存；`subscribe(listener)` 在每次成功保存后回调。不能读别的插件的配置。`save` 不做防抖。
- `host.assets.url(path)`：把宿主交给插件的本地路径转成可显示的 URL；没有授权的路径返回宿主的占位图 URL，不抛错。函数身份在插件加载期间不变。
- `host.pickImages`、`host.pickFiles`（复制进私有暂存区）、`host.pickFilePaths`（只返回原始绝对路径，不读不复制，用时自己校验）、`host.pickDirectory`（取消时 `null`），以及 `onEvent`、`listRoles`、`openExternal`。返回的路径不授予任何宿主资源。

`persona` 默认 `false`，插件逐次选择是否让看板娘出面：`true` / `"generic"` 用该处的通用台词，场景键（`PersonaSceneKey`：`not_configured`、`unauthorized`、`quota`、`network`、`upstream`、`destructive`、`discard`、`confirm`）用宿主为该场景写的台词，表在宿主 `shared/mascot/mascotLines.ts` 的 `personaSceneLines`。台词永远由宿主写，插件只能选场景；用户在 设置 › 外观 关掉看板娘后一律按 `persona: false` 渲染。设计约束见[设计系统](design-system.md)。

## 设置与角色能力卡

- **插件配置的自动表单**：声明了 `config_model` 的插件由宿主生成 schema 表单。编辑停 400 ms（`autosaveDebounceMs`）后合并保存；同一时间只提交一份完整草稿，之后的编辑替换排队中的草稿。离开或切换表单时按原插件 ID 冲刷最后一份草稿；改回已保存的值会取消尚未开始的保存。每次实际改动仍走完整的运行时配置事务（多数情况是[代内重载](plugin-lifecycle.md#代内重载)）。`host.config.save()` 不防抖。
- **私有设置**：`usePrivateAutosave`、`SettingsField`、`SettingsToggleField`、`SettingsGroup`、`SettingsSectionCard`、`settingsInputClass`、`settingsGroupStackClass` 与 `host.ui.SettingsSavedStatus` 组成插件自写设置页的自动保存和布局。
- **角色能力卡**（`roleSettings` → `RoleCapabilityCard`）：`settings` 打开卡片的设置对话框，Esc、点背景、关闭按钮都会关掉并把焦点还给触发按钮。对话框内容首次打开时挂载，关闭后保持挂载，未完成的自动保存和重试不丢；挂载本身不写任何东西，对话框也不持有保存事务。`PluginRoleSettingsProps` 给出 `roleId`（新建角色时为 `null`）、限定作用域的 `client` 和 `moodCatalog`；角色设置在 `PluginHostServicesProvider` 下渲染，换角色时重新挂载。`storage: "plugin"` 配 `read: () => ({})` 让私有设置不进宿主的角色草稿；`onSettingsOpenChange`（`CapabilitySettingsDialog.onOpenChange`）可以在关闭时冲刷自动保存。角色编辑器的未保存提醒只管宿主的角色草稿。

## 后台模块

后台模块在隐藏窗口里运行，`setup(ctx)` 收到 `BackgroundCtx`：

- `rpc`（同上面的 client，另可 `rpc.handle(name, handler)` 登记供 `client.background.call` 调的方法）、`events`（插件内事件）、`hostEvents`（显式订阅宿主事件）；
- `surfaces`（创建、显示、移动 surface，收发消息，`setInteraction(surfaceId, {roleId, available})` 声明交互目标，`null` 撤销）、`store`、`tray`、`assets`（无授权路径返回 `null`）；
- `native`：`audio`（设备、16 kHz 单声道 WAV 采集、播放）与 `keys`（全局快捷键），随后台激活绑定，激活或窗口结束时收回；
- `chat`：`send({role_id, content, turn_id, media})` / `cancel({session_key, turn_id})`；桥接连接开着时，每个被接受的回合以 `chat.done`、`chat.error` 或 `chat.cancelled` 中的恰好一个结束（`chatTerminalEventMethods`）；
- `effect(label, dispose)` 登记清理；`reportFailure(operation, error)` 把已处理但仍需人看到的失败写进宿主的桌面诊断日志（后台窗口的控制台看不到）。

## surface

SDK 4.1.1 起，`surfaces.create` 的 `SurfaceSpec.visible` 可设为 `false`：窗口准备期间保持隐藏，`ready()` 只重放状态，由 background 显式 `show()` 交接。默认值仍是 `true`。

background 可订阅 `surfaceLifecycleEvent`（`surface.lifecycle`），按 `SurfaceLifecyclePayload` 的 `plugin_id`、`surface_id` 和 `window_id` 识别自己的实例。`unavailable` 表示 renderer 重载/崩溃而失去就绪状态，`closed` 表示窗口已销毁；提供者应撤销相应实例的加载或展示，不用心跳推测宿主已知的窗口生命周期。

SDK 4.1.2 起，background 可通过 `hostEvents.on(nativeAudioPlaybackEvent, ...)` 观察自己调用 `native.audio.play` 的实际播放。`NativeAudioPlaybackPayload` 包含 `plugin_id`、`owner`、`generation`、`playback_id`、`phase`（`started` / `level` / `ended`）与 `amplitude`。`level` 约每 33ms 返回唯一 Web Audio 播放流的 RMS（0–1）；开始和结束的音量为 0，结束还带 `reason`（`finished` / `stopped` / `failed`）。该事件经过 native token 与上下文身份校验，只送给播放所属的 background，不进入共享桥接事件流。

调用方可在 `NativeAudio` 中添加可选 `request_id`，将回报关联到自己的队列项；`playback_id` 标识宿主实际的一次播放。先匹配请求号，再接受该播放 ID 的后续音量，取消时立即撤销本地关联。合成、排队、解码均不代表已播放；不得另外播放一份音频来测量音量。`audio.play` 仍在播放完成或停止时结束，已有调用不需修改。

surface 组件收到 `SurfaceHandle`（`PluginSurfaceComponentProps`）。`onRoleActivity(listener)` 只给交互目标可用的 surface 推送 `SurfaceRoleActivity`（`roleId`、`sessionKey`、`phase`、`notify`），目标变化时推 `null`。窗口隐藏、关闭、重载或崩溃都会撤销交互目标。原始后端事件订阅和 `window.miraDesktop` 不是插件 API。语音手势、播放队列等归插件自己（桌宠）。

## 测试入口

`@yinfengwindy/shiori-sdk/testing`：`mountTestComponent` / `changeInputValue` / `mockableWindowTimers`（happy-dom 挂载）、`chooseSelectOption`、`deferred`、`createFakeHostServices`（可断言的内存 `host`）、`createFakeSurfaceHandle`、`createFakePluginClient`。假的 `host.ui` 组件只渲染文本、按钮和 ARIA，不带宿主样式和看板娘，`persona` 在记录下来的 props 上断言。宿主侧的插件 UI 测试用 `pnpm desktop:test:plugin-ui`。

独立构建的示例在 `tests/fixtures/external-plugin/`：复制到仓库外即可用它自己固定版本的 pnpm / esbuild 构建，把 TSX / TS 编成 ESM、把宿主对等依赖设为 external，不需要宿主源码；构建和校验命令见该目录的 README。

`roleSettings` 的 `storage: "plugin"` 贡献可提供 `save(roleId, values, previous, client)`。
回调返回已保存的投影，宿主逐项更新基线；写入成功但后续通知或刷新失败会如实报告已保存。
有此回调时，草稿不进入 `roles.update.plugin_drafts`，宿主先保存核心角色，再调用插件 RPC；
没有回调的贡献仍参加原有的原子角色扩展事务。RPC 失败时核心基线已更新、素材的一次性操作已清空，
插件草稿保留供重试或重置，并明确提示部分保存。两次提交不构成跨 RPC 的原子事务。
`devMode` 是可选的宿主开发模式标志；主动插件借此保持原有开发验证策略的可见性。
