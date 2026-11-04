# 插件私有文件统一到 plugin-data

2026-11-04 维护者确认：场景状态、定时任务、MCP 登记和主动推送诊断日志统一放到各自的 `plugin-data/<id>/`。这些文件的格式保持不变；宿主在冷启动时迁移已有文件，插件随后使用新位置。

本决策覆盖[四层重构](2026-10-22-plugin-system-four-layer-refactor.md) D17、P6s 中保留 `schedules.json` 旧位置的约定，以及场景插件化时沿用 `scene/state.json` 的做法。[P8](2026-11-03-p8-installer-and-gates.md) 删除的通用 `STORAGE` / `migrate_data` 接口不恢复；此次迁移只由 bootstrap 处理下表五个固定文件，不新增 SDK Key 或 Protocol。

## 文件归属

以下路径均相对工作区根目录。

| 旧位置 | 当前位置 | Owner |
| --- | --- | --- |
| `scene/state.json` | `plugin-data/scene/state.json` | scene |
| `schedules.json` | `plugin-data/schedule/schedules.json` | schedule |
| `mcp_servers.json` | `plugin-data/mcp/mcp_servers.json` | mcp |
| `memory/proactive_config_trace.jsonl` | `plugin-data/proactive/logs/proactive_config_trace.jsonl` | proactive |
| `memory/proactive_rate_trace.jsonl` | `plugin-data/proactive/logs/proactive_rate_trace.jsonl` | proactive |

MCP 插件、MCP 自动启用检查和 proactive 的 MCP 客户端读取同一个新登记文件。初始化工作区也只在新位置创建空 MCP 登记与定时任务文件。

## 迁移与失败处理

- 只处理表内现存的旧文件，不递归搬动 `memory/`、`scene/` 或其他目录。
- 新目标不存在时，把旧文件内容发布到新位置；目标已存在时以目标为准，不覆盖、不合并旧内容。
- 每份旧文件归档到 `private_runtime/plugin-storage-archive/<原相对路径>.<sha256>.bak`。摘要由旧文件内容计算；归档保留原始字节，即使新目标已有不同内容也保留旧版本。
- 删除旧路径前核对源文件与归档字节；本次创建的新目标也须与源文件一致，已有目标须保持原内容。写入、校验或清理失败时抛出异常，阻止启动并保留失败文件的原始来源；已完成的文件不回滚。重复启动可继续处理尚未完成的文件。
- 成功后移除旧路径，运行时不再从这些旧位置恢复数据。归档不在插件私有目录中，普通插件数据清理不会删除它，也不会自动从归档恢复状态。

## 接入时机

`serve_bridge` 在配置事务恢复后执行迁移，随后才应用待执行安装/卸载操作、检查 MCP 自动启用并加载配置。这样旧 MCP 登记在自动启用判断前已可读取，用户要求删除插件数据的待执行卸载也会覆盖迁入的数据。

`init_workspace` 在加载配置和预建空文件前执行迁移；直接调用 `AppRuntime.start()` 时也在首次构造 core 前幂等执行。运行时代际准备与热重载不迁移文件，避免触碰运行中的旧代。

## 保留边界

角色关系与好感状态、`roles/<id>/proactive.db`、Drift、角色配置与记忆文档继续归角色生命周期。`proactive_sources.json`、`recovery/shell_restore/`、显式 `AKASIC_RESTORE_DIR` 以及其他插件的旧目录不在此次迁移范围内。

scene 对更早 `scene_awareness` 数据的兼容读取暂时保留：当前状态不存在时，首次真实写入仍可导入旧 KV；写入目标使用 `plugin-data/scene/state.json`。

## 验收边界

定向检查应覆盖旧文件迁入并归档、已有新目标优先、重复运行、失败后原文件保留，以及初始化和正式启动在使用文件前完成迁移。MCP 自动启用与 proactive 读取必须验证新路径；测试只使用临时工作区。迁移通过不代表已经迁移用户本机正在使用的工作区。
