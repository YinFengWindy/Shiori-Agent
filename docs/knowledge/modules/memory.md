---
title: 记忆系统
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - packages/sdk/python/shiori_sdk/memory/
  - apps/backend/core/memory/
  - apps/backend/bootstrap/memory_plugins.py
  - plugins/default_memory/
  - apps/backend/agent/retrieval/
  - apps/backend/conversation/listening_store.py
related:
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# 记忆系统

## 分层

- `packages/sdk/python/shiori_sdk/memory/` 定义 `MemoryEngine`、`MemoryQuery`、变更、ingest 和构造（build）契约；`apps/backend/core/memory/plugin.py` 只保留宿主的 `DisabledMemoryEngine` 并转引这些契约，`core/memory/runtime.py` 的 `MemoryRuntime` 把 Markdown 记忆、选中的引擎和其构造资源装在一起。
- `apps/backend/core/memory/markdown/` 是宿主拥有的 Markdown 记忆层：后台维护队列与整理提交（`maintenance.py`、`consolidation.py`）、近期上下文（`recent_context.py`）、用户层整理（`user_layer.py`，#496）和外部段整理（`external_segment.py`，#497）。
- 记忆分层（#475）中由宿主直接写入、不经过记忆引擎的两层：群环境层 `core/memory/group_environment.py`（每个外部会话的最近动态写在 `thread_state.summary`，群笔记在角色记忆目录 `memory/groups/`）与成员层 `core/memory/member_profiles.py`（按「渠道 + 发送者 ID」一份 `memory/members/` 档案，用户本人不建档）。二者的写入互斥与整理提交时的乐观校验在 `core/memory/external_writes.py`。
- `plugins/default_memory/` 是默认记忆引擎插件：`backend/engine/` 实现 SDK 的 `MemoryEngine`（查询、显式召回的 HyDE 假设生成、变更、管理、提示词），`backend/semantic/` 拥有原 memory2 的 SQLite 存储（`MemoryStore2`，默认 `plugin-data/default_memory/memory2.db`）、向量编码与召回、去重、procedure 查询构造与标签、记忆写入和响应后 worker。原 `apps/backend/memory2/` 已不存在。
- `apps/backend/agent/retrieval/`（`DefaultMemoryRetrievalPipeline`）将具体记忆召回适配到 Agent 上下文准备阶段。

记忆引擎由配置 `memory.engine` 选择，`bootstrap/memory_plugins.py` 只从插件根目录里含 `backend/memory_plugin.py` 的包加载（`default` 对应 `default_memory`），找不到时以「未知 memory engine」报错。Akasha 已从内置插件中移除；显式配置 `memory.engine = "akasha"` 会按未知引擎报错，需改为已安装的引擎后启动。卸载不迁移或删除工作区中原有的 Akasha 数据。

## 典型数据流

回合前根据角色、会话和当前输入构建 `MemoryQuery`，召回结果经过过滤、重排或注入规划进入上下文。回合后由后台 worker 判断是否写入、合并或 supersede 旧记忆。post-response 与 consolidation 两条隐式长期记忆提取链路共用当前角色的 active `profile / preference / procedure` 作为去重上下文；每轮提取受 worker token 预算约束。显式的 `memorize`、`forget_memory`、`recall_memory` 工具复用同一记忆契约。

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
