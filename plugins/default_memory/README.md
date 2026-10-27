# 默认记忆

`backend/semantic/` 拥有 SQLite、向量检索、去重、规则标签及回复后处理。
`backend/engine/` 实现 SDK 的 `MemoryEngine`；宿主 Markdown 层通过
`ConsolidationCommitted` 传递已提交的整理结果，插件等待所有并行写入结束后才传播失败。

`setup(ctx)` 构造默认引擎并 `provide(MEMORY_ENGINE)`。向量凭据只读插件配置
（`embedding_api_key`、`embedding_base_url`、`embedding_model`，`${NAME}` 在
setup 解析，解析不到值的引用也算缺失）；缺任一项则启动失败，不创建数据库。主对话
模型经 `main_provider` / `main_model` 注入。数据库与 embedder 在构造时用 `ctx.effect`
登记清理。宿主检索、记忆工具与总线订阅调用引擎的异步入口，不在内核默认排空之内：
引擎对外的 query / ingest / mutate 与总线 handler 记为在途，`runtime.on_drain` 与关库
前的清理都先等它们结束。同步方法（如 plugin_undo 的 `rollback_turn`）不计数，
调用方在任何 `await` 之后都要重新取引擎。

默认路径仍为 `workspace/plugin-data/default_memory/memory2.db`；显式 `db_path`
照旧。旧配置迁移与 SQLite lease 仍走注入的 storage。库内单行表
`embedding_fingerprint` 记录模型与维度，并核对已有 `vec_items` 的声明维度。
旧库没有指纹表时，首次启动写入；模型或维度不一致则启动失败，不改已有行。

`setup` 声明 memory、rpc、tools、http、events、light_provider、light_model、runtime，
并注入 `main_provider` 与 `main_model`。成功启动后按 `tool_profile()` 经
`ctx.tools` 注册 memorize / forget_memory / recall_memory；用 `ctx.on` 订阅
`TurnStarting` / `ToolCalled` 记录检索与召回轨迹。文档读取由注入能力实现，
插件继续拥有 roles.memory.documents 与 roles.memory.semantic.* RPC 注册及卸载。
独立安装与测试见 [TESTING.md](TESTING.md)。
