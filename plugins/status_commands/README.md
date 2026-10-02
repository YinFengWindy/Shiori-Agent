# status_commands 插件

通过 v2 `setup(ctx)` 注册诊断命令。`lifecycle` 贡献在会话获取后、记忆检索前执行；`bot_commands` 贡献菜单项。命令直接回复，不进入检索或 LLM，也不改写会话消息。停用或装配失败时，两类贡献一起撤销。

## 命令

| 命令 | 别名 | 输出 |
|---|---|---|
| `/memorystatus` | `/memory_status`、`/compact_status` | 当前会话记忆整理位置、尚未整理的真实用户消息数、最后已整理消息预览 |
| `/kvcache` | `/cache_status` | 最近几轮的缓存命中率、token 数量及回复预览 |

`/compact_status` 只读取记忆整理状态。主动压缩上下文使用宿主的 `/compact`；它与桌面输入框圆环共用上下文压缩控制器，不属于本插件。

命令不区分大小写，支持 Telegram 的 `@bot` 后缀。`/kvcache` 默认显示 5 轮，整数参数限制在 1–30；无效参数使用默认值。

## 可选遥测读取

manifest 通过 `optional_dependencies: [observe]` 声明可选读取权限。每次 `/kvcache` 都用 `ctx.dependencies.get_optional("observe")` 取得当前运行代的公开 API，再调用 `recent_cache_turns(session_key, limit=...)`。命令插件不直接打开遥测存储。

observe 的 `ObserveTelemetry` 返回不可变的 `KVCacheTurn` 记录；读取实现、路径和存储结构归 observe 所有。读取不会创建存储。未生成数据时显示“暂无 KVCache 数据。”；observe 未安装、停用、加载失败或没有公开接口时显示明确的不可用回复；存储读取失败显示“KVCache 查询失败。”。

可选依赖不会启动 observe，也不会让状态命令随 observe 一起卸载。observe 重新启用后，下一条命令读取新接口，无需重新注册命令。

独立插件测试安装见 [TESTING.md](TESTING.md)。observe 仅为测试 extra 的依赖，运行 status_commands 不要求安装它。
