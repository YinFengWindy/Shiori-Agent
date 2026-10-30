# 插件前端契约

[插件指南](plugin-guide.md)的专题篇：插件 UI、后台模块和 surface 与宿主之间的 TypeScript 契约。类型的唯一来源是 `@yinfengwindy/shiori-sdk`（源码 `packages/sdk/src/`，契约类型在 `src/contract/`）；运行时导出清单是 `apps/desktop/src/plugins/uiContract.ts` 的 `pluginUiPeerExports`。生成的 [API 参考](plugin-api.md) 只覆盖 Python。与源码冲突时以源码为准。

P7 会统一前端入口（`frontend.entry`），并删掉下面的 `renderer` / `peer_dependencies` 块；在那之前本篇描述的是现行做法。

## 入口与产物

内置插件的源码入口按目录发现：`ui/index.tsx`、`background/index.ts`、`surface/index.tsx`，各自默认导出。外部包在 manifest 的 `renderer.<kind>` 下声明预编译产物：`entry` 是包内 `.mjs`，`css` 是 `.css` 列表（`[]` 表示没有样式）。每个声明的入口和样式都必须存在，缺一个整包在导入后端前就被拒。`node scripts/build-plugin.mjs --plugin plugins/<id> --output artifacts/plugins` 从源码入口编译出这些产物并打 ZIP（要求 `api: 4` 与 `distribution: external`）。

产物是浏览器 ESM，必须有默认导出。CommonJS、格式不明的 `.js`、TypeScript / JSX 源码、空模块、没有默认导出都被拒。静态检查不是完整的 JS 解析器；renderer 加载器在激活前解析完整模块图并校验导出，初始化出错算 `FAILED`，不会部分激活。

| 入口 | 默认导出 |
| --- | --- |
| `ui` | `PluginUiModule`：`{ pluginId, navPage?, settingsSection?, roleAssets?, accountDetail?, roleSettings?, chatImageActions?, roleAffection?, chatAffection? }` |
| `background` | `PluginBackgroundContribution`：`{ pluginId, setup(ctx) }` |
| `surface` | `PluginSurfaceModule`：`{ pluginId, surface: { component } }` |

`pluginId` 必须等于 manifest 的 ID。声明已退役的 `roleMemory`（宿主自己渲染记忆页，记忆插件只提供 `roles.memory.*` RPC）或 `roleUi`（改用 `roleSettings` 卡片，私有设置放 `storage: "plugin"` 的对话框里用 `usePrivateAutosave`）的 UI 模块校验失败。代码不能依赖 Vite glob、宿主源码相对导入或宿主重新构建。

`roleAffection` 挂在角色详情，`chatAffection` 挂在聊天状态栏。宿主只在该插件启用且登记了组件时挂载，两者都注入 `client` 与 `host`。props 只有定位标识：`roleAffection` 是 `{roleId, bridgeReady}`，`chatAffection` 是 `{roleId}`，宿主按角色给 `chatAffection` 加 key，换角色即重新挂载。槽里显示的数据都由插件自己取：好感插件用 `client.call("history" | "chat_status" | "stage_prompts_get" | "stage_prompts_set")`，在 `host.onEvent` 收到本角色的 `session.updated` 后重新读取 `chat_status`（宿主在回合、主动消息、渠道回合存下后广播它，好感记账在此之前完成），不从宿主页面导入，宿主也不读、不转发这些数据。

## 对等依赖与 import map

React、React DOM 和 SDK 主入口是宿主提供的对等依赖，不打进插件包。预编译时把 `react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@yinfengwindy/shiori-sdk` 设为 external，其它浏览器库自己打包。import map 把这些名字解析到包着**宿主自己实例**的 wrapper，所以 hooks、context 和 `instanceof` 与内置插件完全一致。

- 宿主当前保证 React / React DOM `19.2.0`（`host_contract.REACT_API_VERSION`）；`peer_dependencies` 用[指南里的比较语法](plugin-guide.md#sdk-与-peer_dependencies-的比较语法)写范围。
- SDK 主入口能导入的运行时名字只有 `pluginUiPeerExports` 里列出的那些；纯类型导出没有运行时存在。给这张表加名字是契约变更。
- `@yinfengwindy/shiori-sdk/testing` 只用于开发测试，`/contract` 是给主进程和 preload 用的纯类型入口，`/host-internal` 只给宿主；三者都不在 import map 里，插件运行时代码不能导入。
- 插件不得附带或要求安装私有的 npm / Python 运行时依赖。CSS 由插件自带并限定在自己的类名下；共享类名（`cardClass` 等）是 Tailwind 工具串，已在宿主样式表里。

## 资源授权与加载

只有唯一、已启用、`ACTIVE` 的工作区候选拿到资源授权。主进程的 `plugins.list` 回复里带授权后的入口与 CSS URL（`shiori-plugin:` 协议），资源处理器再核对路径和宿主记住的启动时文件哈希，只提供 `.mjs`、`.js`、`.css`、常见图片和字体；新增或改动的脚本、样式、资源一律拒绝。CSP 只放行这个协议和 import map 的哈希，生产环境不加 `unsafe-inline` 脚本或 `unsafe-eval`。替换插件代码后要重启应用。

名册初载、桥接重连、`runtime.applied`、`plugins.changed`、`plugins.reloaded` 和启停开关走同一条串行刷新路径。某个入口导入、样式或导出校验失败时，宿主撤掉这个插件已渲染的部分，在插件管理页显示 `UI FAILED`，并经 `plugins.activation.report` 回报后端，后端把整个插件回滚到 `FAILED` / `RESTART_REQUIRED` 并重新发布名册，其它窗口随之拆掉过期的贡献；其它插件不受影响。

每个入口（和名册行）带一个不透明的 `activation_token`，插件句柄每次变成 `ACTIVE` 都会铸新的。renderer 回报激活结果时原样带回，不匹配就当作未知插件处理。这样停用再启用之后，旧代际里被放弃的加载不能确认或判失败当前句柄。代内重载后，被重载插件的 renderer 入口用新 token 重新回报激活。

## 注入的 client

UI 组件、surface 和后台模块都收到注入的 `client`（`PluginRpcClient`）：

- `client.call(name, payload, { timeoutMs })`：调本插件后端的 RPC。
- `client.events.on(name, handler)`：订阅本插件的事件，返回取消函数。
- `client.dependency(pluginId)`：拿到 manifest `dependencies` / `optional_dependencies` 里声明过的同伴，用同样的本地名调用；可选同伴缺失或未激活时返回 `null`。
- `client.background.call(name, payload)`：调本插件后台模块用 `ctx.rpc.handle` 登记的方法。
- `client.services.list(contract)` / `client.services.call({plugin_id, service_id}, method, payload)`：按契约发现并调用其它插件用 `SERVICES` 发布的服务。不需要静态依赖，也不授予对方私有 RPC 的访问权；提供方或调用方已退役报 `plugin_service_unavailable`，方法未发布报 `plugin_service_method_unavailable`，不会悄悄换成别的提供方。

保留的同伴和已退役上下文发起的调用报 `plugin_unavailable`。组件在注入的 `client` 变化时要重建订阅：真正的运行时发布或桥接重启会替换全部上下文，`plugins.reloaded` 只替换点名的插件；`runtime.applied` 的 `changed: false` 刷新和 `plugins.changed` 不替换仍然 `ACTIVE` 的插件的上下文。

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

surface 组件收到 `SurfaceHandle`（`PluginSurfaceComponentProps`）。`onRoleActivity(listener)` 只给交互目标可用的 surface 推送 `SurfaceRoleActivity`（`roleId`、`sessionKey`、`phase`、`notify`），目标变化时推 `null`。窗口隐藏、关闭、重载或崩溃都会撤销交互目标。原始后端事件订阅和 `window.miraDesktop` 不是插件 API。语音手势、播放队列等归插件自己（桌宠）。

## 测试入口

`@yinfengwindy/shiori-sdk/testing`：`mountTestComponent` / `changeInputValue` / `mockableWindowTimers`（happy-dom 挂载）、`chooseSelectOption`、`deferred`、`createFakeHostServices`（可断言的内存 `host`）、`createFakeSurfaceHandle`、`createFakePluginClient`。假的 `host.ui` 组件只渲染文本、按钮和 ARIA，不带宿主样式和看板娘，`persona` 在记录下来的 props 上断言。宿主侧的插件 UI 测试用 `pnpm desktop:test:plugin-ui`。

独立构建的示例在 `tests/fixtures/external-plugin/`：复制到仓库外即可用它自己固定版本的 pnpm / esbuild 构建，把 TSX / TS 编成 ESM、把宿主对等依赖设为 external，不需要宿主源码；构建和校验命令见该目录的 README。
