# P8 安装器边界与内核门禁

对应 #909，续接四层重构总方案的 D4、D14、D16、D23/D26。P4 已拒绝非 api:4，P5 已启用 SDK 版本约束，P7 已统一前端入口；本次按这些现行职责修订旧方案的按文件删除清单。

## 安装与加载共享准入，不反向依赖 bridge

- ZIP 解包移入 `desktop_bridge/runtime/plugin_package_archive.py`，信任记录移入 `plugin_trust_store.py`。现有预览、确认、安装/卸载事务和失败恢复仍在 bridge。ZIP 确认只记录待执行操作，新应用 session 才发布；bridge 重连不视为应用重启。
- `package_contract`、`package_paths`、`package_schema`、`package_artifacts`、`frontend_contract` 继续属于 `agent.plugin_host`：安装和启动加载都必须验证 API、SDK、前端 peers、产物及路径。把这些规则移到 bridge 再回引会违反既有分层门禁；复制一份校验则会造成两个准入标准。
- bridge 持有信任持久化，bootstrap 把固定 `activation=True` 的 `is_trusted(directory, fingerprint)` 查询传给宿主。宿主不依赖 trust 文件格式、不写批准；查询每次读取最新记录，不缓存。工作区另传给已有的执行身份检查。
- 内容指纹、`PluginExecutionIdentity`、`TrustedPluginImports` 保留在执行侧。执行前再次检查内容，并执行校验过的源码快照；延迟相对导入仍不能绕开快照或改读 pyc。保留 exact-directory / fingerprint / approved_session 及 `private_runtime/plugin-trust.json` version 1。
- 不调整 import-linter 的禁止集合，不新增层、capability 或 SDK Key。过时的「内核（现 agent.plugin_host）」契约改名为「宿主装配层」；「核心模块不 import 插件」已经覆盖全部 `plugins.*`，包括 `plugins.proactive`，无需重复契约。

## 删除旧包装，保留有效公约

`HostRuntimeContract` 已不再代表旧 runtime_api；它剩下的固定 React / React DOM 19.2.0 peer 版本直接归 `frontend_contract`，删除 wrapper 和 `host` 透传参数。

`versions.py` 的 SemVer 与比较器仍供 manifest.sdk、插件版本和 frontend.peers 使用，保留现行语义。拒绝非 api:4 不能替代 SDK/前端版本准入。

`data_migration.py` 的真实复制逻辑在 #883 已删除。2026-11-03 维护者确认在尚未发布的 SDK 4.0 定版中删除剩余空接口：`PrivateStorage.migrate_data`、`STORAGE`、宿主 `PluginStorage` 及其 context/fake 供给一起移除。注册表与 tag 核对的最近已发布 SDK 为 3.1.2，尚无 4.0 正式发布契约；此次属于 4.0 发布前修订，不升 5.0。`MemoryStorage`、`HostMemoryStorage`、`FakeMemoryStorage` 保留实际在用的 `resolve_config` 与 `open_database`；插件路径使用 `plugin_data_dir`。0.5.x 的 `plugin-data/<id>/`、kv、配置与启用状态不变，不恢复旧数据复制。

## 热重载与门禁

`supports_hot_unload` 默认 true；只有证实不能安全卸载的原生扩展才标 false。声明 `contributes.channels` 的插件由宿主判为不可代内重载，TTS/ASR 保持默认可重载。闭包含不可重载插件时整体拒绝代内替换，走需重启路径。`RUNTIME.on_drain` 只等待已接受工作，可重复执行；拆资源仍放 `ctx.effect`。本阶段补齐 AGENTS、schema 与指南，保留已实现的重载行为。

`uv run python -m scripts.kernel_loc_budget` 从报告改为强制门禁：内核 700 代码行通过，701 行失败；缺目录或没有 Python 文件也失败。不计空行、注释和 docstring，不再输出过渡期 plugin_host 基线。现有 import-linter、SDK 边界、宿主与插件 CI 检查继续阻塞。

## 规模与剩余边界

2026-11-03 的修复前基线 `7d2c9f0c` 实测：宿主 `plugin_host` 35 个 Python 文件、5446 物理行 / 3793 代码行；bridge 的 10 个 `plugin_*.py` 文件共 1671 物理行 / 1283 代码行；SDK 内核 7 个 Python 文件共 1077 物理行 / 700 代码行。原方案的宿主装配层/bridge 1.2k–1.5k 与 P8 +250/−2000 都是历史预估，和实际规模存在明显偏差，不能作为当前达标结果。

本次删除空迁移链后的实测如下。物理行按 UTF-8 文本 `splitlines()` 计数；代码行复用 `scripts.kernel_loc_budget.code_lines`，不计空行、注释和 docstring。目录按表中 glob 统计，不把其他宿主或 bridge 模块算入：

| 范围 | Python 文件 | 物理行 | 代码行 |
| --- | --- | --- | --- |
| 宿主装配层 `agent/plugin_host/**/*.py` | 34 | 5419 | 3779 |
| bridge 插件模块 `desktop_bridge/runtime/plugin_*.py` | 10 | 1670 | 1282 |
| SDK 内核 `shiori_sdk/kernel/**/*.py` | 7 | 1077 | 700 |

SDK 内核是 **700/700，没有余量**；满足这一门禁不代表宿主装配层已经完成职责收缩。本轮只处理已确认的残留和文档问题；`plugin_host` 整体职责拆分由维护者另行安排，不在这里新增分层或自行认定规模偏差已解决。

## 发布边界

本次不恢复 Windows 发版 cron，也不触发 Release。P1–P8 的票据与验收全部完成是恢复发版的前置条件；P8 实施或 CI 通过本身不代表已经发布桌面版。
