---
title: 本地工作区数据
kind: 数据说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/core/common/workspace.py
  - apps/backend/core/roles/store.py
  - apps/backend/core/roles/manifest.py
  - apps/backend/session/store/
  - apps/backend/conversation/store.py
  - apps/backend/core/memory/
  - plugins/default_memory/backend/semantic/store/
  - plugins/novelai/backend/storage.py
  - apps/backend/infra/persistence/
  - packages/sdk/python/shiori_sdk/files/
related:
  - ../modules/roles.md
  - ../modules/conversations-and-sessions.md
  - ../modules/memory.md
---

# 本地工作区数据

Shiori 是本地优先应用。默认工作区为 `~/.shiori/workspace`（`core/common/workspace.py:resolve_default_workspace()`），可由 `--workspace` 覆盖。仓库根目录中的 `data/`、`memory/`、`roles/`、`workspace/`、日志和插件 `.data` 属于运行时数据，已被 `.gitignore` 排除。具体位置可受配置或角色工作区影响，不能把仓库内默认路径写死为唯一位置。

## 数据所有权

以下路径均相对工作区根目录；Owning module 路径相对 `apps/backend/`，插件路径相对仓库根目录。

| 数据 | Owning module | 注意事项 |
| --- | --- | --- |
| 角色定义、绑定、素材元数据 | `core/roles/`（`roles/roles.json` 与 `roles/<role_id>/`） | 经过 RoleStore/Service 修改 |
| 角色关系、寂寞与场景追问状态 | `core/roles/relationship_runtime/`、`core/roles/scene_followup_runtime.py`（`roles/<role_id>/state/`） | 随角色删除清理 |
| 活跃 Session | `session/store/`（`sessions.db`） | 包含消息、presence 与搜索 |
| Conversation 线程与群聊旁听 | `conversation/store.py`、`conversation/listening_store.py`（与 Session 共用 `sessions.db`） | 由 service/projector 维护一致性 |
| 角色 Markdown 记忆 | `core/memory/`（`roles/<role_id>/memory`） | 删除角色时级联清理 |
| 默认记忆引擎 | `plugins/default_memory/backend/semantic/store/`（默认 `plugin-data/default_memory/memory2.db`，旧 `memory/memory2.db` 自动迁移；可由插件配置 `db_path` 覆盖） | 带角色、会话和时间/向量索引 |
| NovelAI 设置、生成记录与标签 | `plugins/novelai/backend/`（生成数据在 `plugin-data/novelai/generation`，旧 `private_runtime/novelai` 自动迁移） | 敏感配置不进入 Git |
| 调度任务 | `agent/scheduler.py`（`schedules.json`） | 删除角色时检查引用 |
| 账号投递与用户身份 | `core/accounts/delivery_ledger.py`（`account_deliveries.sqlite3`）、`core/identity/store.py`（`user_identities.json`） | 渠道账号与身份配对 |
| 插件包与插件状态 | `agent/plugin_host/`、`desktop_bridge/runtime/plugin_package_*.py`（外部插件包在 `plugins/`，私有数据与 KV 在 `plugin-data/<id>/`，待执行安装事务在 `private_runtime/plugin-operations/`） | 卸载插件时同时处理私有数据 |

## 持久化原则

JSON 写入复用 SDK `shiori_sdk.files.json` 的 `atomic_save_json()`（文本与字节见 `shiori_sdk.files.text`）；SQLite 由 owning store 管理连接和 schema，事务辅助在 `infra/persistence/sqlite_transaction.py`。迁移应幂等、失败即停并保留可诊断信息。不要在 UI 或渠道适配器中直接编辑运行时文件。

## 备份与迁移验收

验证旧数据读取、新格式落盘、重复运行迁移、部分失败恢复、角色/会话引用完整性、UTF-8 文本、附件路径和回滚前备份。源码和知识库只能说明代码中的数据关系，不能证明某个本地实例的数据健康。
