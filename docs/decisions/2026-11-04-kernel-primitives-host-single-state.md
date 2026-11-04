# 内核原语与宿主单一状态

对应 #977 / #980 / #981 / #982，延续四层方案 D3、D14、D16、D24、D25 与 P8 安装器边界。此项属于尚未发布的 SDK 4.0 定版；P8b 全部子票完成之前不恢复桌面发版。

## 状态归属

`shiori_sdk.kernel.Kernel` 只拥有依赖规划、激活、作用域、排空、释放与生命周期状态。宿主决定本轮激活的候选、检查信任与内容、编排启停及配置回滚。测试的启动、重载、停止由 `shiori_sdk.testing.kernel.KernelHarness` 组合同一组原语，不在生产内核中保留第二套编排。

宿主不保存 `PluginState` / `PluginHandle`，也不把 SDK 状态复制到别的表。其运行记录只包括发现结果 `_records`、实例调用与渲染入口门 `_instances`、一次性预检内容 `_screened`，以及只有宿主知道的首次信任激活失败 `_host_failures`。配置 schema 独立存在：setup 失败后仍可用于修复配置，实际释放候选时才注销。插件导出 API 直接保存在内核提供的 Key 中。

`PluginView` 是读取时生成的快照。下表从上到下取第一项；`plugins.list` 始终只有七种状态。

| 顺序 | 条件 | 展示状态 | 诊断 |
|---|---|---|---|
| 1 | 准入 CONFLICT | CONFLICT | 发现期冲突 |
| 2 | 准入 UNTRUSTED | UNTRUSTED | trust_required / trust_changed |
| 3 | 准入 BLOCKED | BLOCKED | 原准入原因 |
| 4 | 准入 RESTART_REQUIRED | RESTART_REQUIRED | executed_content_changed |
| 5 | 首次信任激活失败 | FAILED | activation_failed |
| 6 | 首次信任激活需重启 | RESTART_REQUIRED | plugin_restart_required |
| 7 | 配置停用 | DISABLED | 无 |
| 8 | 内核 ACTIVE | ACTIVE | 附渲染入口门与激活令牌 |
| 9 | 内核 FAILED，清理完整 | FAILED | setup_failed / renderer_<kind>_failed |
| 10 | 内核 FAILED，清理不完整 | RESTART_REQUIRED | rollback_cleanup_failed |
| 11 | 内核 BLOCKED / REPLACED | BLOCKED | 内核原因，inject 索引转为 manifest 字段 |
| 12 | 内核 None / STOPPED | BLOCKED | not_started |

## 已接受的行为变化

R1：`runnable` 只表示准入通过且启用。失败但启用的插件仍参与重复提供、冲突与替换判定；启动另一个插件不会自动重试它。A、B 都声明同一 Key，A setup 失败、B 原本停用，启用 B 后双方均 BLOCKED，和相同启用集合的冷启动一致。

R2：重载替换或启停过程中的尚未启动成员短暂显示 BLOCKED / `not_started`，设置页不显示问题文案。此时后台没有另一个 LOADING / UNLOADING 状态需要同步。排空尚未释放旧实例时仍保持 ACTIVE；setup 完成后恢复 ACTIVE。`not_started` 不代表准入失败：该名册行仍可切换，启停及卸载的运行期停用通过现有设置事务锁排队；真正的准入 BLOCKED 仍被拒绝。

## 原语与失败边界

- `plan` 清除本次已解除、且没有 scope 的旧规划排除状态；正常停止、setup 失败及正在运行的状态不清除。清理失败的 FAILED 状态不得被冲突规划覆盖，冲突引入或解除均不能抹去重启屏障。
- `deactivate(plugin_id, failure=None, error=None)` 接收显式失败时留下 FAILED 与清理错误，并发 `PluginFailed`。渲染入口失败使用此原语。报告走现有 `PLUGIN_TRANSPORT` 调度通道，等待内核转换锁期间不占全局 mutation 锁或读请求容量，使 `chat.cancel` 等控制请求仍能响应。取得转换锁后再检查当时的激活令牌；其他插件转换完成后仍适用的报告才执行，过期报告不影响后继实例。
- `_prepared` 在任何插件代码导入之前确认宿主创建了本次实例，并一次性消费该候选的预检内容。内容指纹和执行身份先持久化，再执行已核对的源码快照，保持 D16。
- D14 的渠道与不可热卸载闭包整体拒绝保持不变。D25 排空按依赖方到提供方逐个关闭调用门；超时、回调失败或取消时旧门重新开放，实例与配置不变。排空成功之后替换与持久化完成才响应取消。
- setup 被取消、清理又被取消时，仍持有 scope 的实例保留到强制终止，以完成剩余 effect；不因缺少 ACTIVE 状态而丢失清理责任。
- 信任确认只更新候选与准入；不改启用偏好。默认启用目标可以首次激活，等待它的消费者保持 BLOCKED，提供者启动后由正常启用闭包恢复。批准已保存但首次激活未能发布时，由 `_host_failures` 保存失败，不能展示成已停用或成功运行。

## 规模记录

原方案中宿主装配层加 bridge 约 1.2k–1.5k 的历史估计作废。T4 工作树实测如下：物理行按 UTF-8 `splitlines()` 计数，代码行使用 `scripts.kernel_loc_budget.code_lines`；后续 T5 迁移通信与 T6 拆文件仍须重新计量，不能把搬迁当作删除。

| 范围 | Python 文件 | 物理行 | 代码行 |
|---|---|---|---|
| agent/plugin_host/*.py | 31 | 4785 | 3515 |
| desktop_bridge/runtime/plugin_*.py | 10 | 1651 | 1263 |
| shiori_sdk/kernel/*.py | 7 | 1047 | 688 |

内核仍以 700 代码行为硬门禁。宿主 `kernel.py` 此时仍超过 600 物理行，按 T6 沿既定职责边界拆分；T4 尚未迁移通信链；各阶段都不新增层或 SDK Key。


## T5 通信归属与装配

RPC 注册表、renderer 通信、请求等待表、services 注册表与桥接事件迁入 `desktop_bridge/plugin_rpc/`。宿主仅依赖 `renderer_communication.py` 的撤销协议；`CommunicationEndReason` 在该协议旁定义宿主会发出的三种原因，由 bridge 共用。bridge 的请求终止类型以联合类型扩展自己的 `runtime_replaced`，不把整代退役职责放回宿主协议。`rpc_names.py` 仍属于宿主静态准入，因为 manifest 必须拒绝保留的 RPC 命名空间。

`PluginKernel` 通过必填构造参数接收 `communication` 与 `resolve_reference`，不再注册或读取 `HOST_BRIDGE` / `HOST_CONFIG_REFERENCES`。bootstrap 构造后将 `active_peers` 绑定到通信层的 resolver，读取权威的当前活动实例与依赖声明；协议、授权、代际和请求取消语义不变。

账号投递只依赖本模块的 `AccountRpcResolver.resolve` 协议，返回处理函数复用 SDK 的 `RpcHandler`，不反向引用 bridge 的具体注册表类型。默认 bootstrap 契约通过真实启动后的 renderer open 与跨插件 RPC 请求守住 resolver 装配；漏掉绑定时该通信路径直接失败。

`SERVICES` 仍是同一公开 Key，核心提供现有 services 注册表作为 binder。`PluginRuntimeContext.require/get` 缓存它为当前 `PluginBinding` 创建的 `ScopedPluginServices`，其注册仍使用本实例 scope 和调用闸门；宿主 setup 不再构造或访问 RPC/services 注册表。

T5 工作树实测（同上口径）：

| 范围 | Python 文件 | 物理行 | 代码行 |
|---|---|---|---|
| agent/plugin_host/*.py | 27 | 4221 | 3075 |
| desktop_bridge/runtime/plugin_*.py | 10 | 1651 | 1263 |
| desktop_bridge/plugin_rpc/*.py | 6 | 551 | 424 |
| shiori_sdk/kernel/*.py | 7 | 1047 | 688 |

宿主与两组 bridge 插件模块合计从 T4 的 6436 物理行 / 4778 代码行变为 6423 / 4762。通信迁移主要改变职责归属，净减少仅 13 物理行 / 16 代码行；不能把宿主目录的缩小当作整体删除。T6 继续拆分宿主大文件。
