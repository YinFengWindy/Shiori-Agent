# 插件生命周期与准入

[插件指南](plugin-guide.md)的专题篇：插件从被发现到运行、重载、停用的规则。内核在 `packages/sdk/python/shiori_sdk/kernel/`，宿主编排在 `apps/backend/agent/plugin_host/`（`kernel.py`、`reload.py`、`unload.py`）与 `apps/backend/desktop_bridge/runtime/apply.py`。与源码冲突时以源码为准。

## 状态

| 状态 | 含义 |
| --- | --- |
| `UNTRUSTED` | 外部包可读 manifest，但在用户确认信任之前不运行任何代码 |
| `BLOCKED` | 静态契约、SDK 约束、依赖不可用、依赖成环或重复提供，改正后重试 |
| `FAILED` | 导入或 setup 失败，已回收它登记的资源 |
| `CONFLICT` | 多个候选声明同一个插件 ID 或同一个渠道名，一个都不选 |
| `RESTART_REQUIRED` | 已执行过的代码目录变了，或回滚没能完全释放资源，要等下次启动 |
| `REPLACED` | 被另一个插件的 `replaces` 取代（内核层） |
| `DISCOVERED`、`DISABLED`、`LOADING`、`ACTIVE`、`UNLOADING`、`DISPOSED` | 普通运行周期 |

启用 / 停用偏好与代码版本、重启状态分开保存；更新不会悄悄重新启用已停用的插件。

## 规划

每一轮启动（应用启动、代际替换、代内重载或启停）先把全部 spec 交给内核 `plan`，再由 `Kernel.start` 依次 setup。规划规则（`shiori_sdk/kernel/graph.py`）：

- **顺序**：依赖深度，再按插件 ID。深度由 `inject` 和 `optional_inject` 指向的提供方算出。这个顺序就是 setup 顺序、`on` 链与 watcher 的顺序，也是工具钩子、渠道和命令的聚合顺序，代内重载后不变。只登记的 spec 也参与排序，好让排名稳定。
- **重复提供**：两个可运行插件 `provides` 同一个 Key、又没有 `replaces` / `conflicts` 关系时，双方都 `BLOCKED`（`duplicate_provider`），谁也不赢。
- **与核心撞名**：可运行插件 `provides` 了宿主已经提供的核心 Key，`plan` 直接抛 `KernelError`，整代启动失败。只登记的插件声明核心 Key 不会让规划失败。
- **成环**：只有 `inject`（硬依赖）能成环，而且只有当环上每个成员都可运行时才拒绝，成员都 `BLOCKED`（`dependency_cycle`）。`optional_inject` 可以互相引用，只用于排序。
- **`replaces` / `conflicts`**：内核 spec 的字段，只在可运行的 spec 之间判定；manifest 目前没有对应字段。

## 只登记的插件

spec 的 `runnable = False` 表示只登记：已停用、未信任、准入失败（契约无效、缺宿主依赖）、本轮选中但不启动，或者 setup 失败 / 被释放之后都会重新规划成只登记，这样别人的 `start` 不会顺带把它跑起来。

- `Kernel.activate` 拒绝只登记的 spec，抛 `KernelError("not_runnable")`，状态不变，不会变成 `ACTIVE`。
- 只登记的插件不参与重复提供、`replaces` / `conflicts` 和成环判定。可运行插件依赖它时不算环：可运行的一方照常排序，之后因依赖不可用被 `BLOCKED`，不会被报成 `dependency_cycle`。只登记的成员本身不被标 `BLOCKED`，也不发 `PluginFailed`。
- 没有可运行插件认领某个 Key、但有只登记的插件声明了它时，这个 Key 记在 ID 最小的那个只登记插件名下。依赖它的插件因此得到 `dependency_unavailable`（「未启用或加载失败」），而不是 `missing_dependency`（「不存在」，没有任何插件声明这个 Key）。两者的诊断都是 stage `dependency`、field `inject[<序号>]`。
- 后面某一轮再选中它（`load`、依赖拉起、代内重载或启用、代际替换）时重新规划为可运行并重试。

## 预执行闸门

外部包的信任与执行身份检查在**规划之前**、由宿主做，不在内核里：本轮要启动的每个工作区包都重新核对内容指纹和执行身份。被拒的包把宿主句柄设成 `UNTRUSTED` 或 `RESTART_REQUIRED`，并按只登记规划，所以它从不被导入，内核不给它记状态、不发 `PluginFailed`，也不排除别人（比如它的重复提供对手照常启动）。setup 导入的正是核对过的那份字节（保存在内存里，不重读）。作为兜底，宿主没准备过的启动（没有 `LOADING` 句柄、已停用、内容未核对）会被拒绝并成为内核的 `setup_failed`。

## 启动与失败

- 硬依赖的 Key 没有提供方：`BLOCKED`，见上节两种诊断码。
- setup 抛错：内核先释放它登记的一切（提供的 Key、订阅、任务、effect），状态 `FAILED`（`setup_failed`），发 `PluginFailed`；硬依赖它的插件随后 `BLOCKED`。
- setup 成功：`ACTIVE`，发 `PluginStarted`，宿主为它铸一个新的 `activation_token`（见[前端契约](plugin-frontend.md#资源授权与加载)）。
- `start` 被取消：还没轮到的插件恢复原来的句柄状态，不会停在 `LOADING`。

## 代内重载

在设置页保存插件配置（`plugin.config.set`）时，宿主在**当前代**里重载目标插件，不发布新的运行代际，`generation` 不变：

- **重载集合**：目标，加上正在运行、用 `inject` 或 `optional_inject` 依赖它的插件（这样没有人保留旧实例的引用）。集合外的插件不重新 setup，它们的效果（托管服务、渠道连接）保留。
- **只能重启的情况**：集合里有声明了 `contributes.channels` 的插件、`supports_hot_unload: false` 的插件，或目标不是 `ACTIVE`，就改走代际替换（`runtime.applied` 且 `changed: true`，或 `plugin_restart_required`）。已停用插件的配置只存表，不重载。
- **排空**：集合里的插件依次排空，总共最多等 60 秒（`PLUGIN_RELOAD_DRAIN_TIMEOUT_SECONDS`）。默认排空只等正在执行的 `on` / `watch` 处理器；`RUNTIME.on_drain` 登记的回调再等插件自己已接受的工作。后台任务不排空，释放时取消。
- **失败码**（新配置都不写入，设置页保留草稿）：
  - 排空超时：`plugin_reload_busy`，`details.plugin_ids` 是仍在忙的插件，什么都没变，旧实例继续服务。
  - 新配置 setup 失败：恢复旧配置和旧实例，`plugin_reload_failed`，带 `details.plugin_ids` 与 `details.restore_failed`（没能按旧配置恢复、留在 `FAILED` 的插件）。
  - 新实例起来后写配置文件失败：同样回滚，`runtime_commit_failed`，带相同的 details。
- **成功后**：桥接发 `plugins.reloaded`（`{generation, plugin_ids}`，目标在前），renderer 只替换这些插件的通信上下文、后台作用域和原生会话。同一 `operation_id` 的重试返回记住的结果，不再发事件。`plugin.config.set` 没有桥接默认的 30 秒请求期限。

插件可观察的语义：

- 新实例 setup 时 `RUNTIME.was_active` 为 `True`，启动恢复逻辑不要重复跑。代际替换时，上一代处于 `ACTIVE` 的插件在新一代 setup 时也是 `True`。
- 一旦实例开始重载、卸载或终止，对它的工具、RPC 处理器和服务的调用，包括通过早先拿到的引用，都以 `PluginRpcError("plugin_unavailable")` 拒绝，不会到达旧实例。
- `on_drain` 回调**只等待已接受的工作，不得拆资源**。它可能执行多次，也可能在实例继续存活时执行（排空超时放弃重载后旧实例重新开放）。拆资源放在 `ctx.effect`。
- 用 `PROCESS_RESOURCES` 拿到的进程资源在代内重载之间保留，新实例重新获取到的是同一个对象。SDK 的托管运行时 helper（`shiori_sdk.managed.rpc.register_runtime_rpc`）在释放时停服务，不在 `on_drain` 里停。

## 启用与停用

设置页的启停开关（`plugins.setEnabled`）也在当前代里完成：

- **停用**：释放目标和正在运行、硬依赖它的插件，**不排空**：`on_drain` 不跑，后台任务（包括 `spawn_runtime`）取消，调用以 `plugin_unavailable` 拒绝，进程资源关闭。目标变 `DISABLED`，依赖方变 `BLOCKED`。目标原本是 `FAILED` 或因依赖 `BLOCKED` 时只变成 `DISABLED`。
- **启用**：setup 目标和只因它而 `BLOCKED` 的插件，`was_active` 为 `False`。setup 失败的插件留在 `FAILED`，开关照样保存。
- 结果里的 `reloaded_plugins` 与 `plugins.reloaded` 事件同上；renderer 刷新名册，停用插件的 surface 随名册消失而关闭。写配置失败时恢复原状态，报 `runtime_commit_failed`。
- 与重载相同的只能重启的情况（渠道、`supports_hot_unload: false`），以及启用时依赖了只有重新加载才能重试的插件（比如 `FAILED`），改走代际替换。

安装、更新、卸载外部包总是走代际替换或下次启动，见下文。

## 诊断

静态拒绝抛 `PackageContractError`，诊断是 `PluginDiagnostic`：

```json
{"code": "missing_file", "stage": "validation", "field": "renderer.surface.entry",
 "reason": "原始的文件系统错误或契约拒绝原因", "path": "renderer/surface.mjs", "state": "BLOCKED"}
```

`code` 给机器读；`field` 指出哪条声明，`reason` 保留原因，`path` 在涉及文件时给出。`stage` 是 `validation`、`discovery`、`trust`、`dependency`、`setup`、`reload` 或某个 renderer 入口类型。名册（`plugins.list`）保留校验诊断，包括格式错误的外部 manifest。运行时失败保留原始错误，不复用静态 `BLOCKED` 诊断。校验通过不等于已信任、已激活或能在每个 renderer 里运行。

## 信任与外部包

工作区里的外部包先是 `UNTRUSTED`。桌面工作区打开后，对已启用、合法、不冲突的候选弹出信任确认；已停用的等用户启用，或在 设置 › 插件 里点「信任…」。取消什么都不授予，本次桌面会话内不再提示该候选（包括 renderer 刷新与桥接重连）。确认后保存精确授权，首次启用的候选在当前应用里经正常加载或安全的代际替换激活。

- 授权存在 `private_runtime/plugin-trust.json`，绑定候选路径和包目录全部发布文件名与字节的 SHA-256。任何源码、manifest、JS、CSS、资源变动都使授权失效。授权不改变启用偏好。
- `private_runtime/plugin-executions.json` 记录本次 Electron 会话里已执行过的外部包；已执行内容变化后要重启应用（桥接重连也一样）。它不是授权。
- 包内容里的符号链接 / junction 被拒；外部 Python 命名空间只编译核对过的源码字节，不加载字节码或原生扩展。
- ZIP 安装与更新（`plugins.install.preview` / `confirm` / `cancel`）和卸载（`plugins.uninstall`）都要显式确认，操作记在 `private_runtime/plugin-operations/`，下次启动时生效。ZIP 限 4096 个成员、解压后 64 MiB；路径只接受规范的相对 `/` 段。卸载默认保留 `plugin-data/<id>/` 与 `[plugins.<id>]`，勾选「同时删除插件数据」才在启动时删除；卸载总是撤销授权。
- 内置包由宿主拥有，不能通过这些操作覆盖或卸载。

打包后的验收流程见[打包插件验收](packaged-plugin-acceptance.md)。
