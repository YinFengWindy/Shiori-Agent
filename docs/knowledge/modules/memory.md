---
title: 记忆系统
kind: 领域说明
status: 当前有效
last_verified_commit: 7def9666
source_paths:
  - packages/sdk/python/shiori_sdk/memory/
  - apps/backend/core/memory/
  - apps/backend/bootstrap/memory.py
  - apps/backend/bootstrap/memory_config_migration.py
  - apps/backend/bootstrap/memory_optimizer_config_migration.py
  - plugins/memory_optimizer/
  - plugins/default_memory/
  - apps/backend/agent/retrieval/
  - apps/backend/conversation/listening_store.py
related:
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# 记忆系统

## 分层

- `packages/sdk/python/shiori_sdk/memory/` 定义 `MemoryEngine`、`MemoryQuery`、变更和 ingest 契约；`shiori_sdk.core.memory` 的 `MEMORY_ENGINE` 是插座，宿主不构造引擎，也没有 `DisabledMemoryEngine`。`core/memory/runtime.py` 的 `MemoryRuntime` 把 Markdown 记忆和 `EngineGetter` 装在一起：getter 在内核建好后绑定到这一代的 `kernel.get(MEMORY_ENGINE)`，可以是 None。消费方（被动检索、桌面端删角色、主动检索、plugin_undo）每次使用时调用 getter，不长期持有引擎（D25）。`plugin_undo` 在插座非空时先用 `SESSIONS.last_passive_turn` 读出整轮，`rollback_turn(锚点用户消息 id, 整轮消息 id)`，再 `SESSIONS.rollback_last_turn(expected_turn=预读的整轮)`；锁内选出的锚点或整轮消息 id 与预读不一致时不删，如实告诉用户上一轮对话未撤销。插座为空只回滚会话。记忆回滚失败则会话不动。
- `apps/backend/core/memory/markdown/` 是宿主拥有的 Markdown 记忆层：后台维护队列与整理提交（`maintenance.py`、`consolidation.py`）、近期上下文（`recent_context.py`）、用户层整理（`user_layer.py`，#496）和外部段整理（`external_segment.py`，#497）。
- 记忆分层（#475）中由宿主直接写入、不经过记忆引擎的两层：群环境层 `core/memory/group_environment.py`（每个外部会话的最近动态写在 `thread_state.summary`，群笔记在角色记忆目录 `memory/groups/`）与成员层 `core/memory/member_profiles.py`（按「渠道 + 发送者 ID」一份 `memory/members/` 档案，用户本人不建档）。二者的写入互斥与整理提交时的乐观校验在 `core/memory/external_writes.py`。
- `plugins/default_memory/` 是默认记忆引擎插件：`backend/engine/` 实现 SDK 的 `MemoryEngine`（查询、显式召回的 HyDE 假设生成、变更、管理、提示词），`backend/semantic/` 拥有原 memory2 的 SQLite 存储（`MemoryStore2`，默认 `plugin-data/default_memory/memory2.db`）、向量编码与召回、去重、procedure 查询构造与标签、记忆写入和响应后 worker。原 `apps/backend/memory2/` 已不存在。
- `plugins/memory_optimizer/` 是后台记忆整理系统插件（#907 P6b，默认启用）：按间隔把各角色 `PENDING.md` 并进 `MEMORY.md`、再更新 `SELF.md`，用角色自己的对话模型（`MODELS`）。整理循环是插件的进程资源（`memory-optimizer-v1`），跨代只有一份，每代 setup 只把本代的 `ROLES` / `MODELS` / `MARKDOWN_MEMORY` 与间隔挂上去；循环只用已发布代的那一份（间隔也从它读，未发布时不跑），某一轮出错只记日志、跳过这一轮，在途整理所在代退役时取消（PENDING 快照回滚）并在当前代重跑该角色。停用插件即关闭资源：循环停止、在途整理取消回滚。文档读写经宿主端口 `MARKDOWN_MEMORY`（`shiori_sdk.core.markdown_memory`，宿主 `core/memory/markdown/host.py`）：读 MEMORY/SELF、写 SELF、PENDING 两阶段提交（`snapshot_pending` → `commit_long_term` / `rollback_pending_snapshot`）、首版 SELF 是否待生成，以及角色 `memory_init_state` 里插件自有的键（`last_memory_optimized_at`、`self_rules_version`）；宿主自己的初始化键（`core/roles/memory_service.py` 的 `HOST_MEMORY_STATE_KEYS`）读不到、写入被拒，值必须可 JSON 序列化。插件 provide `MEMORY_OPTIMIZER`（`active_run()`），桌面任务面板据此列出「记忆维护」。开关只看插件启停；间隔是 `[plugins.memory_optimizer].interval_seconds`。启动时 `[agent.maintenance]`（及顶层同名回退键）的 `memory_optimizer_enabled = false` 迁成插件 `enabled = false`、间隔迁成 `interval_seconds`（不小于 60），与默认值相同的不写，插件表已有的键不覆盖，迁完删除旧键。
- `apps/backend/agent/retrieval/`（`DefaultMemoryRetrievalPipeline`）将具体记忆召回适配到 Agent 上下文准备阶段。

语义记忆的开关是谁在这一代里提供了 `MEMORY_ENGINE`。`default_memory` 在 `setup` 里按插件配置构造引擎并 `provide`；`[plugins.default_memory].enabled` 显式优先，缺省沿用 manifest 的 `default_enabled`（开启）。向量凭据只读这张表（`embedding_model` / `embedding_api_key` / `embedding_base_url` / `output_dimensionality`），不回退到对话模型凭据；解析后仍残留 `${...}` 的值视为缺失。缺凭据，或 `memory2.db` 里 `embedding_fingerprint`（单行 model + dim）/`vec_items` 声明维度与当前配置不一致，插件 FAILED、插座为空，对话仍继续；没有指纹表的旧库在第一次成功 setup 时写入。自定义 `db_path` 指向被检查的那一个库。启动时若 `config.toml` 仍有 `[memory]`，或者这张表还没有显式的 `enabled`，会按旧加载语义一次性写入这张表并删掉 `[memory]`：旧版没有 `[memory]` 或没写 `memory.enabled` 都算关闭，旧开关优先于插件表里已有的 `enabled`；向量凭据写入旧逻辑实际生效的来源（含 `[llm.fast]`、顶层 `light_*` 与首个模型注册的回退），`${NAME}` 引用按原样写回、不展开成明文。模板 `config.example.toml` 显式写 `enabled = true`，所以只有从模板新建的工作区默认开启；迁移后的显式 `enabled` 即已迁移标记。内联表或点分键写法无法定位替换，迁移直接报错并保留原文件。`memory.engine` 不是空或 `default` 时记一条警告并忽略；引擎只经插件接入。Akasha 已从内置插件中移除，旧配置里的 `memory.engine = "akasha"` 不会再被选中。卸载不迁移或删除工作区中原有的 Akasha 数据。角色记忆面板按当前 ACTIVE 且真正提供了 `MEMORY_ENGINE` 的插件显示；没有提供者时显示「记忆已关闭」。

## 典型数据流

回合前根据角色、会话和当前输入构建 `MemoryQuery`，召回结果经过过滤、重排或注入规划进入上下文。回合后由后台 worker 判断是否写入、合并或 supersede 旧记忆。post-response 与 consolidation 两条隐式长期记忆提取链路共用当前角色的 active `profile / preference / procedure` 作为去重上下文；每轮提取受 worker token 预算约束。显式的 `memorize`、`forget_memory`、`recall_memory` 工具在 `plugins/default_memory/backend/tools/`，由插件 `setup` 经 `ctx.require(TOOLS)` 按引擎 `tool_profile()` 注册；bootstrap 不再注册它们。它们复用同一记忆契约。

记忆整理按 `conversation/context_scope.py` 的上下文划分分段：用户本人的发言走用户层，提炼成 HISTORY 事件条目与 PENDING 候选写入角色记忆目录，再交给记忆引擎；群友、陌生人的发言及角色在外部会话的回复走外部段，每个会话单独调用一次 LLM，产出该会话的最近动态、群笔记更新和成员档案（含一行速记），由宿主写入群环境层与成员层。整理不对准备阶段加锁，提交时比对快照，期间被小手机或 `update_group_context` 改过就整次放弃、游标不动，下次重来。

群聊旁听记录（#538，`conversation/listening_store.py`）按群单独整理（#541，`core/memory/markdown/listening.py` / `listening_trigger.py`）：记录入库时和定时全量检查时在后台触发，产物与外部段相同，用户本人在群里的发言同样走用户层；只推进该群的旁听游标，不动角色会话的整理游标，失败只记日志等待下次重试。

注入侧：用户上下文回合注入近三天内更新过的外部会话最近动态（至多五个）和「用户最近在群里说过」块（`core/memory/user_group_speech.py`，#539）；外部上下文回合注入当前会话的群笔记、其他外部会话的最近动态以及当前窗口相关成员的档案。

`memorize` 返回结构化 JSON；post-response worker 优先解析该结构获取本轮受保护的 `item_id`，同时保留旧文本结果的读取兼容。角色删除时桌面桥接调用记忆引擎的 `invalidate_role_memories()`（默认引擎落到 `MemoryStore2.invalidate_role_memories()`）失效该角色的结构化记忆，不影响其他角色。

## 修改影响

- 修改记忆记录 schema：检查 store、向量索引、时间索引、迁移、去重和管理工具。
- 修改召回评分：检查注入阈值、默认记忆插件的 HyDE 辅助查询、上下文 token 预算和评测；不要无意重写原始 score。
- 修改角色/群聊隔离：检查查询过滤、权限策略、会话键、上下文划分和响应后写入。
- 修改群环境层或成员层：检查整理外部段、旁听整理、小手机编辑、`lookup_group_context` / `update_group_context` 工具和乐观校验。
- 修改生命周期接入：检查 `BeforeTurn` 上下文准备和响应后的异步整理，不要阻塞消息投递。

## 不变量

- 角色和会话的记忆域必须显式过滤，不能依赖提示词约束实现隔离。
- 召回结果与持久化记录分离；派生分数不应破坏原始证据。
- 后台整理失败必须留下可查询的明确原因。
- post-response 处理失败必须向生命周期边界冒泡，不能静默跳过角色记忆错误。
- 群环境层与成员层只由宿主写入，不经过记忆引擎；用户本人不产生成员档案。
