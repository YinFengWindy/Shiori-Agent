# 记忆系统——Markdown 文件层

Shiori 的记忆分为两层：**Markdown 文件层**（人类可读，LLM 直接写入）和**向量数据库层**（记忆引擎插件，默认 `default_memory` 的 `memory2.db`，语义检索）。本文档主要讲 Markdown 层——哪几个文件、各自干什么、consolidation 怎么把对话变成记忆。

---

## 五个 Markdown 文件

记忆按角色隔离，都在当前角色的 `~/.shiori/workspace/roles/<role-id>/memory/` 下（`core/memory/role_paths.py` 的 `role_memory_dir`）。
文件骨架（标题与固定段落）定义在 `core/memory/markdown_schema.py` 的 `DOCUMENT_DEFAULTS`，标题都是中文：

| 文件 | 写者 | 读方 | 用途 |
|------|------|------|------|
| **MEMORY.md** | Optimizer（主 agent 自动维护） | 被动/主动 agent 的 system prompt（外部回合不注入） | 长期记忆——用户的稳定事实、偏好、身份。固定段落：`## 关于你` / `## 你的偏好` / `## 你希望我记住的事` |
| **SELF.md** | Optimizer（主 agent 自动维护） | 被动/主动 agent 的 system prompt（外部回合只注入「性格与形象」「我们的关系」两段） | 角色的自我认知。固定段落：`## 我的性格与形象` / `## 我对你的理解` / `## 我们的关系` |
| **HISTORY.md** | Consolidation worker 自动追加；Optimizer 归档时也追加一条 PENDING 归档记录 | 主 agent 浏览宏观时间线时读取（`prompts/agent.py`）、consolidation 自身（取最近 3 条做上下文） | 按时间线的事件日志（`# 我们的共同经历`），只追加不修改 |
| **RECENT_CONTEXT.md** | Consolidation worker 自动维护（只用用户上下文的消息） | 被动/主动 agent 的 system prompt（外部回合不注入） | 近期上下文摘要——最近在聊什么、关注什么 |
| **PENDING.md** | Consolidation worker 追加 → Optimizer 消费后清空 | Optimizer | 缓冲队列——从对话中提取的待归档事实 |

同目录下还有 `journal/YYYY-MM-DD.md`（按天的事件日记）和幂等库 `consolidation_writes.db`。

### 外部会话的两层（#497 / #498）

角色在群聊、陌生私聊等外部会话里的内容不进上面五个文件，而是由宿主在整理提交时写进另外两层（不经过记忆引擎）：

- **群环境层**（`core/memory/group_environment.py`）：每个外部会话的「最近动态」（一两句，存在会话状态 `thread_state.summary`）和群笔记 `memory/groups/*.md`。
- **成员层**（`core/memory/member_profiles.py`）：群友、陌生人每人一份档案 `memory/members/*.md`（宿主维护的 JSON 头 + 印象正文），以「渠道 + 发送者 ID」识别；用户本人不建档。

用户本人在群里说的话仍归用户层，照常提取进 HISTORY / PENDING。旁听记录（#541）按群另行整理，见 `core/memory/markdown/listening.py`。

---

## Consolidation：对话怎么变成记忆

每次 agent 回复完后会触发一次 consolidation 检查。不是每条消息都触发——有一个最小新消息数的门槛。

记忆整理进度与模型原文窗口分开持久化。普通整理只更新记忆游标、语义产物及消费者状态，不移出模型历史。窗口准备移出原文时，会通过 `ensure_memory_for_window` 补齐对应类别的未整理前缀；即使未达到平时门槛也执行，已整理范围跳过。具体归属、迁移和提交条件见 [模型输入预算](context-budget.md)。

### 什么时候触发

```
TurnCommitted 事件
  → MarkdownMemoryMaintenance._should_consolidate_session()
    → 有未完成的消费者（pending_consumers）→ 直接整理
    → 否则检查：(新消息数 - 保留数 - 上次 consolidate 的位置) >= min
       keep_count = memory_window 向上对齐到 4 的倍数再除以 2（默认 40 → 20）
       min = max(5, keep_count // 2)
       角色会话按用户上下文 / 外部上下文各自计数，互不影响（#523）
  → 够了就调 consolidation，不够就只刷新 RECENT_CONTEXT.md 的「最近的对话」块
```

### Consolidation 干了什么

一次 consolidation（`core/memory/markdown/consolidation.py` 的 `prepare_consolidation`）先把窗口按发送者拆段，再分别调用 LLM，然后写文件：

```
待整理窗口（角色会话按发送者拆段）
    ├─ 用户本人段（文本格式）
    │     ↓
    │   LLM 提取用户层（user_layer.py 的提示词，一次调用；没有用户本人发言就不调）
    │     ↓
    │   产出两样东西：
    │     1. history_entries[]  — 时间线事件，每条 {summary: "1-2句摘要", emotional_weight: 0-10}
    │     2. pending_items[]    — 可归档的长期事实，每条 {tag: "identity|preference|...", content: "..."}
    │
    └─ 外部段（群友、陌生人的发言与角色在外部会话的回复）
          ↓
        按会话各调一次 LLM → 最近动态、群笔记、成员档案与速记（写群环境层 / 成员层）
    ↓
  用户层按顺序写入：
    • HISTORY.md    — 追加 history_entries（幂等，按 source_ref 去重）
    • PENDING.md    — 追加 pending_items（幂等，按 source_ref 去重）
    • RECENT_CONTEXT.md — 再用一次 LLM 调用生成「最近聊过的事」摘要（整篇覆盖，只取用户上下文的消息）
    • journal/YYYY-MM-DD.md — 同 history_entries，按天分文件
```

**HISTORY.md 格式**：每条一行，前面有不可见的 consolidation 标记（`<!-- consolidation:["msg_id1","msg_id2"]:history_entry -->`），正常渲染看不到。

```
[2026-05-09 14:30] 用户开始学习 Rust 语言，购买了《Rust程序设计》第二版。
[2026-05-09 15:00] 用户表示不喜欢悬疑压抑风格的游戏。
```

**PENDING.md 格式**：每条 `- [tag] 内容`，支持 6 种 tag：

| Tag | 含义 | 例子 |
|-----|------|------|
| `identity` | 稳定身份事实 | `- [identity] 用户是互联网公司产品经理` |
| `preference` | 稳定偏好/禁忌 | `- [preference] 用户不喜欢悬疑压抑风格的游戏` |
| `key_info` | 密钥/账号/ID | `- [key_info] 用户的 GitHub 用户名是 example` |
| `health_long_term` | 长期健康事实 | `- [health_long_term] 用户有慢性偏头痛` |
| `requested_memory` | 用户明确要求记住 | `- [requested_memory] 项目 deadline 是 6 月 15 日` |
| `correction` | 更正已有记忆 | `- [correction] 更正：用户不是学生，已毕业` |

**RECENT_CONTEXT.md 格式**：

```markdown
# 最近发生的事

## 最近聊过的事
until: 2026-05-09T15:00:00
- 最近持续关注：用户最近在讨论记忆检索架构重构
- 最近明确偏好：偏好低压力、能长期坚持的创作方式
- 最近待延续话题：上次未完成的代码讨论
- 最近避免事项：不要在不适当的时机讨论技术架构

## 还在继续的事
- 用户最近持续受睡眠问题影响，情绪低落

## 最近的对话
<!-- a-preview = assistant reply preview only -->
[user] 我头有点疼，可能昨晚没睡好
[a-preview] 先休息一下，不要勉强
```

（旧文件里的英文标题 `## Compression` / `## Ongoing Threads` / `## Recent Turns` 读取时仍然认得。角色会话生成的文件开头还会带一行宿主写入的可见范围标记 `<!-- shiori-recent-context:v1 ... -->`，见 [模型输入预算](context-budget.md)。）

「最近聊过的事」由单独一次 LLM 调用生成，有严格规则：**只从 USER 消息里提取，不把 assistant 的建议当事实**。「最近的对话」部分是轻量的——每次 turn 后单独刷新，不触发完整 LLM 调用。

### 幂等性保证

`consolidation_writes.db`（SQLite）用 `source_ref`（一条 JSON 数组，比如 `["msg_001","msg_002"]`）做主键，同一批消息不会写两次。HISTORY.md 和 PENDING.md 内部的隐藏标记也做第二层保护。

记忆文件写入和游标提交成功后，下游 memory2 事件或关系刷新失败不会回滚记忆。会话持久化保存消费者输入和版本，下一次维护继续未完成阶段；事件已发布时不再重复发布。近期语境刷新也独立记录来源消息和更新版本，关系记录其已消费的记忆版本。

PENDING.md 还有两阶段提交：`snapshot_pending()` → Optimizer 处理 → `commit_pending_snapshot()` 或 `rollback_pending_snapshot()`。启动时如果发现残留 snapshot 会自动回滚合并，防止崩溃丢数据。

---

## PENDING → MEMORY：Optimizer 怎么归档

PENDING.md 只是缓冲——consolidation 把新事实写进 PENDING，但 PENDING 不注入 system prompt。真正的长期记忆 MEMORY.md 交给一个定时任务（Optimizer）来更新。

**为什么要隔一层？为了缓存。**

MEMORY.md 是全文注入 system prompt 的。如果每次 consolidation 都直接改 MEMORY.md，那每轮对话的 system prompt 都不一样 → DeepSeek 的 prompt cache 永远命中不了 → 每轮都多花几秒和一份 cache_write token。Optimizer 把 MEMORY.md 的更新频率降到 18 小时一次，中间攒在 PENDING.md 里不动它，让 prompt cache 能稳定命中几十上百轮。

```
consolidation (每 N 条消息触发一次)
    ↓
  写入 PENDING.md（高频追加，不改 MEMORY.md）
    ↓
  MEMORY.md 保持不变 → prompt cache 持续命中
    ↓
Optimizer (定时触发)
    ↓
  读 MEMORY.md + PENDING.md → LLM 归档 → 一次性地更新 MEMORY.md → 清空 PENDING.md
    ↓
  MEMORY.md 变化一次 → prompt cache miss 一次 → 下一轮重新建立缓存
```

### Optimizer 怎么工作的

```
PENDING.md（增量事实缓冲区）
    ↓
  Optimizer 定时触发（默认 memory_optimizer_interval_seconds = 64800）
    ↓
  读 MEMORY.md + PENDING.md → LLM 做归档决策：
    • 新事实 → 写入 MEMORY.md 对应分类
    • 与已有条目冲突 → 更新或替换
    • 重复 → 忽略
    • 更正 → 用 correction tag 的内容覆盖旧条目
    ↓
  备份旧 MEMORY.md，写入新的 MEMORY.md
  HISTORY.md 追加一条「PENDING 归档」记录
  commit_pending_snapshot() → 清空本次处理的 PENDING（合并返回空时 rollback_pending_snapshot()，原样保留）
    ↓
  第二步：更新 SELF.md，只改写三个固定段落
  （SELF 写入规则带版本号 SELF_RULES_VERSION；角色记录的版本落后时，这一步换成按新规则一次性重写）
```

实现在 `proactive_v2/memory_optimizer.py`，按角色逐个优化；启动时先补跑已经超期的角色，之后按间隔对齐触发。
开关和间隔在 `config.toml` 的 `[agent.maintenance]`：`memory_optimizer_enabled`（默认 true，且要有模型注册才会启动）、`memory_optimizer_interval_seconds`（默认 64800，最小 60）。

普通会话的消息数阈值继续触发后台记忆整理。模型请求前还会按注册容量、本次输出预留和安全余量检查完整输入；触发线默认是窗口的 75%，目标为 40%，二者均受可用输入上限约束。
超过触发线时由 `CompactionController` 先补齐待移出范围的记忆、再写工作摘要并移出原文；压缩后仍不满足预算或整理失败时停止请求。配置与 provider usage 锚点详见 [模型输入预算](context-budget.md)。

---

## 这些文件怎么进入 System Prompt

每次回复前构建 system prompt 时，按 priority 顺序依次渲染（完整清单见 `agent/core/prompt_block.py` 顶部注释）：

| Priority | 块名 | 来源文件 | 注入形式 |
|----------|------|---------|---------|
| 30 | SelfModel | `SELF.md` | `## 角色自我认知\n\n{全文}`；外部回合只取「我的性格与形象」「我们的关系」两段 |
| 35 | LongTermMemory | `MEMORY.md` | `## Long-term Memory\n{全文}`；外部回合不注入 |
| 45 | RecentContext | `RECENT_CONTEXT.md` | 「最近聊过的事」+「还在继续的事」（不含「最近的对话」，那个有独立的滑动窗口）；外部回合不注入 |
| 46 | RecentActivity | 群环境层的最近动态 | 近 3 天更新过的外部会话，最多 5 个；外部回合只列其他外部会话 |
| 47 | GroupNote | `memory/groups/*.md` | 当前外部会话的群笔记，只在外部回合注入 |
| 48 | MemberProfiles | `memory/members/*.md` | 触发者与 @/回复对象的完整档案、窗口内其他成员的速记，只在外部回合注入（放 context frame） |
| 49 | UserGroupSpeech | 角色会话群聊里的用户发言 + 旁听记录 | 用户最近 6 小时在群里说过的话（最多 10 条），只在用户上下文注入（放 context frame） |
| 55 | MemoryBlock | 向量检索结果 | 记忆引擎 `query(intent="context")` 的语义召回块；外部回合不注入 |

**注意**：MEMORY.md 和 SELF.md 是**全文注入**的，不做截断或检索——这也是为什么 Optimizer 需要保持它们紧凑。HISTORY.md 不直接注入 prompt，只在主 agent 需要浏览宏观时间线时读取，以及给 consolidation 自身做上下文。

---

## 文件流转总览

```
用户发消息
    ↓
system prompt 注入：SELF.md + MEMORY.md + RECENT_CONTEXT.md + 向量检索块
    ↓
LLM 回复（记忆在上下文里）
    ↓
TurnCommitted
    ↓
┌─ 新消息不够 → 只刷新 RECENT_CONTEXT.md 的「最近的对话」块
└─ 新消息够了 →
    ├─ LLM 提取 history_entries + pending_items（用户本人段）
    ├─ LLM 按会话整理外部段 → 群环境层 / 成员层
    ├─ 写入 HISTORY.md（追加，幂等）
    ├─ 写入 PENDING.md（追加，幂等）
    ├─ 写入 RECENT_CONTEXT.md（LLM 生成「最近聊过的事」+ 刷新「最近的对话」）
    └─ 写入 journal/YYYY-MM-DD.md（追加）
    ↓
Optimizer 定时任务
    ├─ 读 PENDING.md + MEMORY.md → LLM 归档 → 更新 MEMORY.md
    ├─ commit_pending_snapshot()
    └─ 更新 SELF.md
```

两层记忆的分工：**Markdown 层**管"人类能看懂的全景"——你是谁、你喜欢什么、最近发生了什么。**向量层**管"机器能搜到的细节"——语义检索、时间过滤、去重计数。两个层各自独立更新，通过 `ConsolidationCommitted` 事件桥接——markdown 层写完用户层产物后发事件（只含用户本人段，外部段不进引擎；窗口里没有用户本人发言就不发），向量层（default_memory）收到后把同批数据 embed 写入 `memory2.db`。

---

## 向量记忆 API——谁在调它

`packages/sdk/python/shiori_sdk/memory/engine.py` 定义了一套抽象协议（`MemoryEngine`），由四个子协议组成。引擎本身是一个 **plugin**——`[memory].engine` 配置项指定用哪个实现，留空或 `default` = `default_memory` 插件；`[memory].enabled = false` 时宿主换成 `DisabledMemoryEngine`。协议与实现解耦。

检索和写入各只有一个入口：检索统一走 `query(MemoryQuery)`，用 `intent` 区分场景（`context` / `answer` / `timeline` / `interest` / `procedure`，`effect` 区分 `stateful` / `read_only`）；写入统一走 `mutate(MemoryMutation)`，用 `kind` 区分 `remember` / `forget`。

### API 协议一览

**MemoryIngestApi** — 程序化内容摄入

| 方法 | 用途 |
|------|------|
| `ingest(request)` | 摄入一条内容（目前宿主没有调用方） |

**MemoryRetrievalApi** — 语义检索

| 方法 | 调用方 |
|------|--------|
| `query(MemoryQuery(intent="context"))` | 被动回复每轮自动检索（注入 system prompt） |
| `query(MemoryQuery(intent=...))` | `recall_memory` 工具（LLM 主动调用，intent 默认 `answer`，可选 `timeline` 等） |
| `query(MemoryQuery(intent="interest", effect="read_only"))` | proactive tick 中评估内容候选时 |

**MemoryWriteApi** — 写入/删除

| 方法 | 调用方 |
|------|--------|
| `mutate(MemoryMutation(kind="remember"))` | `memorize` 工具（用户要求"记住..."） |
| `mutate(MemoryMutation(kind="forget"))` | `forget_memory` 工具（用户纠正错误记忆） |
| `reinforce_items_batch(ids)` | 仅 default_memory 内部调用，无外部调用点 |

**MemoryAdminApi** — 管理与描述

| 方法 | 调用方 |
|------|--------|
| `list_role_filter_values(role_id)` / `list_items_for_admin(...)` / `get_item_for_admin(id)` | default_memory 自己的角色记忆面板 RPC（`plugins/default_memory/backend/role_memory.py`） |
| `update_item_for_admin(id, ...)` / `delete_item(id)` / `delete_items_batch(ids)` / `find_similar_items_for_admin(id)` | 管理用途，宿主没有调用点 |
| `invalidate_role_memories(role_id)` | 删除角色时由宿主调用（`desktop_bridge/service.py`） |
| `tool_profile()` | 宿主注册记忆工具时读取：由引擎声明 `memorize` / `forget_memory` / `recall_memory` 的描述、参数和风险（`agent/tools/meta/register.py`） |
| `describe()` | 引擎描述 |
| `keyword_match_procedures(tokens)` | 关键词匹配过程（仅 default_memory 内部） |
| `list_events_by_time_range(start, end)` | 时间范围事件列表（仅 default_memory 内部） |

### 调用点汇总

所有不在 `plugins/default_memory/` 下的真实调用点（不写行号，行号会漂）：

| 位置 | 方法 | 说明 |
|------|------|------|
| `apps/backend/agent/retrieval/default_pipeline.py` | `query(intent="context")` | 被动 turn 每轮的语义检索入口。`DefaultMemoryRetrievalPipeline.retrieve()` 把回合上下文转成 `MemoryQuery` 交给 `engine.query()` |
| `apps/backend/agent/tools/recall_memory.py` | `query()` | `recall_memory` 工具。LLM 传入 query / intent / memory_kind / 时间范围 / limit，工具组装成 `MemoryQuery` |
| `apps/backend/proactive_v2/tools.py` | `query(intent="interest")` | proactive tick 中评估内容候选时调用，查询用户对某条内容是否可能感兴趣 |
| `apps/backend/agent/tools/memorize.py` | `mutate(kind="remember")` | `memorize` 工具。用户要求"记住..."时调用 |
| `apps/backend/agent/tools/forget_memory.py` | `mutate(kind="forget")` | `forget_memory` 工具。用户纠正错误记忆时调用 |
| `apps/backend/core/memory/runtime.py` | `query()` / `mutate()` | `MemoryRuntime` 薄封装层，统一入口 |
| `apps/backend/core/memory/plugin.py` | 全部方法 | `DisabledMemoryEngine` — 记忆关闭时的空实现，所有方法都返回空/报错 |

### 引擎如何注入

```
bootstrap/memory.py → engine = plugin_runtime.engine（记忆关闭时 DisabledMemoryEngine）
    ├── register_memory_meta_tools(tools, engine) → 按 engine.tool_profile() 注册 memorize / forget_memory / recall_memory
    ↓
  MemoryRuntime(markdown=..., engine=...)
    ↓
    ├── 被动 reply: DefaultMemoryRetrievalPipeline → engine.query(intent="context")
    └── 插件宿主服务 memory_engine → 声明 memory_engine capability 的插件通过 ctx.memory_engine 访问
    ↓
  proactive_v2/tools.py → ToolDeps.memory → query(intent="interest")
```

调用方拿到的都是协议类型（`MemoryRetrievalApi` / `MemoryWriteApi` / `MemoryAdminApi`），不是 `DefaultMemoryEngine`。换引擎实现只需要改 `config.toml` 的 `[memory].engine`。
