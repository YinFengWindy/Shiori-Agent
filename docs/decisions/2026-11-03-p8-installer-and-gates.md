# P8 安装器边界与内核门禁

对应 #909，续接四层重构总方案的 D4、D14、D16、D23/D26。P4 已拒绝非 api:4，P5 已启用 SDK 版本约束，P7 已统一前端入口；本次按这些现行职责修订旧方案的按文件删除清单。

## 安装与加载共享准入，不反向依赖 bridge

- ZIP 解包移入 `desktop_bridge/runtime/plugin_package_archive.py`，信任记录移入 `plugin_trust_store.py`。现有预览、确认、安装/卸载事务和失败恢复仍在 bridge。ZIP 确认只记录待执行操作，新应用 session 才发布；bridge 重连不视为应用重启。
- `package_contract`、`package_paths`、`package_schema`、`package_artifacts`、`frontend_contract` 继续属于 `agent.plugin_host`：安装和启动加载都必须验证 API、SDK、前端 peers、产物及路径。把这些规则移到 bridge 再回引会违反既有分层门禁；复制一份校验则会造成两个准入标准。
- bridge 持有信任持久化，bootstrap 把固定 `activation=True` 的 `is_trusted(directory, fingerprint)` 查询传给宿主。宿主不依赖 trust 文件格式、不写批准；查询每次读取最新记录，不缓存。工作区另传给已有的执行身份检查。
- 内容指纹、`PluginExecutionIdentity`、`TrustedPluginImports` 保留在执行侧。执行前再次检查内容，并执行校验过的源码快照；延迟相对导入仍不能绕开快照或改读 pyc。保留 exact-directory / fingerprint / approved_session 及 `private_runtime/plugin-trust.json` version 1。
- 不调整 import-linter 的禁止集合，不新增层、capability 或 SDK Key。

## 删除旧包装，保留有效公约

`HostRuntimeContract` 已不再代表旧 runtime_api；它剩下的固定 React / React DOM 19.2.0 peer 版本直接归 `frontend_contract`，删除 wrapper 和 `host` 透传参数。

`versions.py` 的 SemVer 与比较器仍供 manifest.sdk、插件版本和 frontend.peers 使用，保留现行语义。拒绝非 api:4 不能替代 SDK/前端版本准入。

`data_migration.py` 的真实复制逻辑在 #883 已删除。本次将仅解析目标路径的实现内联到 `PluginStorage`，删除独立模块。SDK 4.0 的 `PrivateStorage.migrate_data`、`STORAGE` 和 `MemoryStorage` 公开面继续保留，不因仓库内暂无调用而做破坏性删除。0.5.x 的 `plugin-data/<id>/`、kv、配置与启用状态不变，不恢复旧数据复制。

## 热重载与门禁

`supports_hot_unload` 默认 true；只有证实不能安全卸载的原生扩展才标 false。声明 `contributes.channels` 的插件由宿主判为不可代内重载，TTS/ASR 保持默认可重载。闭包含不可重载插件时整体拒绝代内替换，走需重启路径。`RUNTIME.on_drain` 只等待已接受工作，可重复执行；拆资源仍放 `ctx.effect`。本阶段补齐 AGENTS、schema 与指南，保留已实现的重载行为。

`uv run python -m scripts.kernel_loc_budget` 从报告改为强制门禁：内核 700 代码行通过，701 行失败；缺目录或没有 Python 文件也失败。不计空行、注释和 docstring，不再输出过渡期 plugin_host 基线。现有 import-linter、SDK 边界、宿主与插件 CI 检查继续阻塞。

## 发布边界

本次不恢复 Windows 发版 cron，也不触发 Release。P1–P8 的票据与验收全部完成是恢复发版的前置条件；P8 实施或 CI 通过本身不代表已经发布桌面版。
