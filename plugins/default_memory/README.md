# 默认记忆

`backend/semantic/` 拥有 SQLite、向量检索、去重、规则标签及回复后处理。
`backend/engine/` 实现 SDK 的 `MemoryEngine`；宿主 Markdown 层通过
`ConsolidationCommitted` 传递已提交的整理结果，插件等待所有并行写入结束后才传播失败。

`MemoryPlugin.build(deps)` 接收 SDK 的必要模型/embedding 配置以及模型、HTTP、
事件、技能列表、角色权限、存储与构造资源能力。每个分配立即登记清理，完整构造后
显式 transfer，由宿主维护成功生命周期；失败时外层构造作用域清理已登记资源。
宿主只路由 `validate_transition`，具体向量维度和配置路径规则归插件。

默认路径仍为 `workspace/plugin-data/default_memory/memory2.db`；显式 db_path、
旧配置迁移、迁移凭证和仍在使用的数据库拒绝迁移规则保持原状。数据迁移和 SQLite
lease 使用注入的宿主 storage 能力，共享原来的锁。修改已有向量空间仍必须显式迁移。

`setup(ctx)` 声明 memory、rpc、lifecycle 和 events。文档读取由注入能力实现，
插件继续拥有 roles.memory.documents 与 roles.memory.semantic.* RPC 注册及卸载。
独立安装与测试见 [TESTING.md](TESTING.md)。
