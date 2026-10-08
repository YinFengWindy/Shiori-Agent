# Proactive 主动推送

Shiori 不只是被动回复——它每 N 秒/分钟跑一轮 tick，检查你订阅的信息源，自主决定"现在该不该给你发消息、发什么"。没有内容可推时就进入 **Drift 空闲任务**。

## 先理解它是什么

> 把 proactive 和 drift 想成两个**独立的小 agent**，各带一套固定工具，各自醒来干活。

### Proactive：一个定时醒来的"要不要发消息"决策器

Proactive 本质上是：

1. **一套固定工具**（`proactive_v2/tools.py` 的 `TOOL_SCHEMAS`）：`get_alert_events`、`get_content_events`、`get_context_data`、`recall_memory`、`get_content`、`web_fetch`、`web_search`、`get_recent_chat`、`mark_interesting`、`mark_not_interesting`、`message_push`、`finish_turn`，外加共享的 `account_list` / `account_targets`
2. **一段固定 system prompt**（角色身份 + 固定规则，在 `agent/core/proactive_turn/prompt_context.py` 的 `build_system_prompt()`）
3. **一个 MCP 数据源池**：从你配置的 server 拉 alert / content / context

每次 tick 做的事非常机械：**把 MCP server 返回的数据灌进 prompt → LLM 按 prompt 指令逐条判断 → 调用工具写分类结果 → 如果有内容值得推就 message_push 完事**。

```
[外部 MCP server 数据] + [你的 PROACTIVE_CONTEXT.md 规则] + [长期记忆]
        ↓
   灌进 system prompt
        ↓
   LLM 调工具做 mark_interesting / mark_not_interesting
        ↓
   有 interesting → 写一条消息 → message_push → 发给你
   没有 → finish_turn(skip)
```

**决策逻辑在哪里？都在 prompt 里。** 你没有写代码，你写的是 `PROACTIVE_CONTEXT.md` 里的白名单/黑名单/过滤规则，以及 `proactive_sources.json` 里告诉它去哪拉数据。剩下的"这条内容发不发"的判断，全是 LLM 自己根据 prompt 做的。

### Drift：一个没东西可推时才醒来的"后台干活"执行器

当 proactive 拉了一圈发现——没有 alert、没有 content，也没有可走的关系兜底（relationship fallback）——它会进入 Drift。Drift 跟随角色的主动推送开关，主动推送开着就开。

Drift 跟 proactive 的**根本区别在于控制方式**：

| | Proactive | Drift |
|---|---|---|
| **行为由谁定义** | 固定 system prompt（代码里写死的） | `SKILL.md` 文件（你写的，放在当前角色的 `roles/<role-id>/drift/skills/` 下；模型选中后用 `read_file` 读） |
| **做什么** | 分类、筛选、决定推不推 | 你定义什么就做什么（审记忆、问问题、自我诊断...） |
| **工具** | 推送决策专用工具（mark_*, message_push, finish_turn） | 通用工具（read_file, write_file, fetch_messages, shell...）+ 可 message_push 一次 |
| **收尾** | finish_turn(decision=reply/skip) | finish_drift(message_result=sent/silent) |

写一个 drift skill 就是写一份 `SKILL.md`，告诉模型：
- 你这次的任务是什么
- 有哪些工作文件（读什么、写什么）
- 每一步怎么做（像 SOP 一样）
- 什么时候发消息、什么时候静默

**proactive 是"筛选推送引擎"，drift 是"用户可编程后台任务"。**

### 两者的关系

```
proactive tick
  └── DataGateway 拉数据
       ├── 有 alert/content → 跑 proactive agent loop（prompt 驱动）
       ├── 都没有，但准入 gate 选中了关系兜底 → 跑纯关系向的 proactive loop
       └── 啥都没有 → 跑 drift（SKILL.md 驱动；受 min_interval_hours 冷却）
```

就这么简单。下面展开讲怎么配、怎么跑。

---

## 配置步骤

### 哪些你写、哪些 agent 写

配 proactive 涉及的 workspace 文件分两类：

| 文件 | 维护方式 | 说明 |
|------|---------|------|
| `roles/roles.json` 里角色的 `proactive` | **你配**（桌面角色的「主动推送」） | 每个角色自己的开关、接收会话、推送策略（profile）、agent/drift 参数、overrides |
| `mcp_servers.json` | **你写** | MCP server 启动命令和环境变量。也可以通过对话让 agent 调 `mcp_add` 工具写 |
| `proactive_sources.json` | **你写** | 声明哪个 MCP server 提供哪类数据（alert/content/context） |
| `roles/<role-id>/PROACTIVE_CONTEXT.md` | **agent 维护** | 当前角色的推送规则面板。主 agent（被动回复时）通过对话帮你写和改。proactive agent 只读不写 |
| `schedules.json` | **都行** | 建议让主 agent 调内置的 `schedule` 工具增删改，或在桌面里给角色建任务；手写时字段要求见下文 |
| `roles/<role-id>/drift/skills/*/SKILL.md` | **你写** | 当前角色的 Drift 任务定义。也可以用内置 skill `create-drift-skill` 让 agent 帮你生成 |
| `roles/<role-id>/memory/*.md` | **agent 维护** | 长期记忆、自我认知、近期上下文——全部由主 agent 通过被动对话自动读写 |
| `roles/<role-id>/drift/drift.json` | **agent 维护** | 当前角色的 Drift runner 自动写运行记录，不用管 |

### 1. 开启 proactive（角色的「主动推送」）

主动推送按角色配置、按角色各跑一个 loop（`bootstrap/proactive.py` 只为开启了主动推送的角色建 loop）。配置存在 `roles/roles.json` 里该角色的 `proactive` 对象，平时在桌面角色的「主动推送」里改：开关、接收会话、推送策略（profile），以及执行参数（每次推送最大步数、候选内容数、网页上下文字符数、空闲活动最大步数与最小间隔）。结构如下（用 TOML 写法示意）：

```toml
enabled = true
profile = "daily"           # daily / quiet；dev_verify 只在开发模式下可选

[agent]                     # 只允许这三个键，多写会报错
max_steps = 20
content_limit = 5
web_fetch_max_chars = 8000

[drift]                     # 只允许 enabled / max_steps / min_interval_hours
max_steps = 20              # 默认 20，最小 3
min_interval_hours = 3      # 默认 3，0 表示不限
```

`drift.enabled` 只为兼容旧快照而接受，不起作用——Drift 跟随主动推送开关。`config.toml` 里的 `[proactive]` 段仍会做校验，但运行时以角色自己的配置为准；全局的 `target` / `default_channel` 等投递目标键已移除，写了会报错。

投递目标同样不在这里写死：每个角色在「主动推送」里勾选接收会话，每条主动消息只发到其中一个（桌面在场时发桌面，否则发最近对话过的外部会话）。

### 2. 注册 MCP server（`~/.shiori/workspace/mcp_servers.json`）

```json
{
  "servers": {
    "fitbit": {
      "command": ["/path/to/fitbit-mcp/.venv/bin/python", "/path/to/fitbit-mcp/run_mcp.py"],
      "env": {},
      "cwd": "/path/to/fitbit-mcp"
    },
    "feed": {
      "command": ["/path/to/feed-mcp/.venv/bin/python", "/path/to/feed-mcp/run_mcp.py"],
      "env": {},
      "cwd": "/path/to/feed-mcp"
    }
  }
}
```

MCP server 通过 stdio 与 agent 通信，启动时 `McpClientPool.connect_all()` 建立常驻连接。也可以用内置工具 `mcp_add` 让 agent 帮你加。

### 3. 声明信息源（`~/.shiori/workspace/proactive_sources.json`）

把 MCP server 的工具映射到 proactive 通道：

```json
{
  "sources": [
    {
      "server": "fitbit",
      "channel": "alert",
      "get_tool": "get_proactive_events",
      "ack_tool": "acknowledge_events",
      "enabled": true
    },
    {
      "server": "fitbit",
      "channel": "context",
      "get_tool": "get_sleep_context",
      "enabled": true
    },
    {
      "server": "feed",
      "channel": "content",
      "get_tool": "get_proactive_events",
      "ack_tool": "acknowledge_events",
      "poll_tool": "poll_feeds",
      "enabled": true
    },
    {
      "server": "steam",
      "channel": "context",
      "get_tool": "get_steam_context",
      "enabled": true
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `server` | 对应 `mcp_servers.json` 里的 key |
| `channel` | `"alert"` / `"content"` / `"context"` |
| `get_tool` | MCP tool 名。content/alert 默认 `get_proactive_events`，context 默认 `get_context` |
| `ack_tool` | 确认工具。alert/content 需要，context 不需要（不走 ACK） |
| `poll_tool` | content 专用：周期拉新的 tool（如 `poll_feeds`） |

### 4. 写推送规则（`~/.shiori/workspace/roles/<role-id>/PROACTIVE_CONTEXT.md`）

这是当前角色主被动 loop 共享的规则面板，文件不存在时 proactive loop 启动会按模板建一份。（注意：主 agent 的系统提示词 `prompts/agent.py` 里写的路径目前仍是工作区根目录的 `PROACTIVE_CONTEXT.md`，和 proactive loop 实际读取的角色目录不一致。）你通过**被动对话**让主 agent 帮你写和维护。proactive agent 每轮只读。

```
# Proactive Context

## CS2 新闻推送过滤规则

**白名单队伍**：HLTV Top 15（每周一更新）+ TyLoo + BC.Game + 100 Thieves
**过滤逻辑**：仅推送白名单队伍及选手相关新闻，其他一律过滤
```

规则要点：写结论不写过程、主 agent 负责维护、proactive agent 每轮读取。**怎么改：直接跟 agent 聊天说"帮我在 proactive context 里加一条规则..."**。

### 5. 定时任务（`schedules.json`）

优先通过主 agent 对话让它调 `schedule` 工具增删（或在桌面里给角色建任务）。文件在 `~/.shiori/workspace/schedules.json`，根节点必须是数组；每个任务都属于一个角色，手写时 `role_id`、`fire_at`、`created_at` 必填，缺 `role_id` 整个文件加载失败：

```json
[
  {
    "trigger": "every",
    "tier": "soft",
    "role_id": "<role-id>",
    "fire_at": "2026-05-09T23:00:00+00:00",
    "created_at": "2026-05-08T10:00:00+00:00",
    "cron_expr": "0 7 * * *",
    "timezone": "Asia/Shanghai",
    "channel": "telegram",
    "chat_id": "7674283004",
    "prompt": "查询北京今天全天天气预报...",
    "name": "通勤天气决策",
    "enabled": true
  }
]
```

`trigger` 取 `at` / `after` / `every`（`every` 配 `cron_expr` 或 `interval_seconds`）；`tier` 取 `instant`（直接发 `message`）/ `soft`（让 agent 按 `prompt` 处理后再发）。

### 6. tick 间隔——不是固定的

tick 不是一个 cron，它是一个**根据你上次说话时间动态变化**的间隔。

```
你上次发消息的时间
    ↓
compute_energy(last_user_at) → 当前"电量" [0, 1]
    三条衰减曲线叠加（30分钟/4小时/48小时）
    刚聊完 → 电量 ≈ 1.0（满）
    半天没聊 → 电量 ≈ 0.0（空）
    ↓
d_energy = 1 - energy → "饥渴度"
    电量满 → 不饿 → d_energy 低
    电量空 → 饿了 → d_energy 高
    ↓
base_score = w_e × d_energy
    ↓
next_tick_from_score(base_score)
    base_score > 0.20 → s1
    base_score ≤ 0.20 → s0（最慢）
```

**直觉**：你刚说完话，agent 不想烦你，慢悠悠地查（8 分钟一次）。你半天没动静，agent 觉得"该找点东西了"，加速查到 4 分钟一次。

三种预设只是调整这张"饥渴→间隔"的映射表：

| 预设 | s0（不饿） | s1（很饿） | 适用场景 |
|------|-----------|------------|----------|
| `daily` | 8 min | 4 min | 日常 |
| `dev_verify` | 1 min | 30 s | 开发调试 |
| `quiet` | 30 min | 15 min | 低打扰 |

每次 tick 后重新算，间隔持续变化——不是定时器，是自适应循环。

### 7. 微调参数（overrides）

同样写在角色 `proactive` 对象的 `overrides` 里（TOML 写法示意）：

```toml
[overrides.gate]
judge_send_threshold = 0.65    # 提高发送门槛

[overrides.trigger]
tick_interval_s0 = 600         # 不饿时 10 分钟
tick_interval_s1 = 180         # 很饿时至少 3 分钟
```

只允许白名单键（`proactive_v2/presets.py` 的 `ALLOWED_OVERRIDE_KEYS`）：`trigger` 下 `tick_interval_s0` / `tick_interval_s1` / `tick_jitter`，`gate` 下 `score_llm_threshold` / `judge_send_threshold` / `judge_balance_daily_max`，`safety` 下 `delivery_dedupe_hours` / `message_dedupe_recent_n`。阈值必须在 [0, 1]，`tick_interval_s0 ≥ tick_interval_s1 ≥ 1`。

---

## 系统怎么跑的（技术展开）

```
ProactiveLoop.run()
  ├── McpClientPool.connect_all()         # 启动时连接所有 MCP server（常驻连接）
  ├── feed poll loop（后台）               # 周期性调用 poll_feeds 拉新内容
  └── tick loop（自适应频率）
       ├── _next_interval(score)           # 电量模型 → 下次 tick 间隔
       ├── DataGateway.run()               # 三路并行预取（alert / content / context）
       │    ├── _fetch_alerts()            # 调 MCP tool: get_proactive_events(kind=alert)
       │    ├── _fetch_content()           # 调 MCP tool: get_proactive_events(kind=content) → 并行 web_fetch 正文
       │    └── _fetch_context()           # 调 MCP tool: get_context / get_sleep_context / get_steam_context
       ├── ProactiveTurnPipeline（agent/core/proactive_turn/）
       │    ├── Pre-gate（ProactiveGateChain：全局准入 + 各动机 gate，如场景跟进、关系兜底；被拦下就跳过本轮）
       │    ├── 无 alert/content 时：关系兜底或 drift（见上文）
       │    ├── agent loop（LLM 逐条评分分类 → mark_interesting/mark_not_interesting → message_push → finish_turn）
       │    ├── Classification completeness check（未分类条目强制补完）
       │    └── Reflection pass（有 interesting 但没收尾时注入提示）
       ├── Post-loop（delivery 去重 / 消息语义去重 → 发送或跳过）
       └── ACK（已消费事件标记为已处理，设置 TTL 防止重复拉取）
```

关键设计点：
- **常驻 MCP 连接**：启动时 `connect_all()`，整个生命周期不复连，避免每次 tick 重启子进程
- **数据先到齐再决策**：三路预取在 agent loop 之前完成，单源失败不影响其他源
- **去重分层**：delivery 级（同一批内容不重复发）+ message 级（语义去重，新消息和最近主动消息如果实质重复也跳过）
- **ACK 机制**：每个被消费的事件都要 ACK，带不同 TTL（cited 168h / interesting uncited 24h / 发送前被去重等守卫拦下 24h / discarded 720h，见 `agent/core/proactive_turn/resolution.py`）

---

## 数据从哪来——MCP 接口契约

三种事件通道各有自己的 MCP tool 约定和返回 schema。这是**写 MCP server 的人需要遵守的合同**——只要满足这个合同，你的数据源就能被 proactive 消费。

### 1. Alert 通道

**设计语义**：高优先级、时效性强的告警，bypass 内容评分，直接透传 agent。

**MCP tool 约定**：`get_proactive_events()` 返回 `list[dict]`，每个 dict 的 `kind` 为 `"alert"`。

**标准 schema**（以 fitbit 为例）：

```json
{
  "event_id": "fb_20260508_001",
  "kind": "alert",
  "source_type": "health_event",
  "source_name": "fitbit",
  "title": "hr_elevated_rest",
  "content": "静息心率异常升高：当前 92 bpm（基线 68 bpm），持续 15 分钟",
  "severity": "high",
  "published_at": "2026-05-08T14:30:00",
  "suggested_tone": "关切但不过度紧张",
  "metrics": {"current_bpm": 92, "baseline_bpm": 68, "duration_min": 15}
}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `event_id` | string | 是 | ACK 的唯一标识 |
| `kind` | string | 是 | 固定 `"alert"` |
| `source_name` | string | 是 | 可读来源名 |
| `title` | string | 是 | 事件类型 |
| `content` | string | 是 | 人类可读告警正文 |
| `severity` | string | 否 | `"high"` / `"medium"`。`"high"` 时 bypass 评分直接推 |
| `published_at` | string | 否 | ISO 时间戳 |
| `suggested_tone` | string | 否 | LLM 语气提示 |
| `metrics` | dict | 否 | 结构化指标，最多 8 key，value 最长 60 字符 |

**ACK tool**：`acknowledge_events(event_ids: list[str])` — alert 走独立 ACK 通道，无 TTL（一次性消费）。

**真实实现**：`~/.shiori/workspace/mcp/fitbit-mcp/src/mcp_bridge.py`：

```python
@mcp.tool()
def get_proactive_events() -> str:
    data = _fetch_agent_payload(timeout=5)
    raw_events = data.get("health_events") or []
    events = [_to_standard_event(e) for e in raw_events]
    return json.dumps(events, ensure_ascii=False)
```

### 2. Content 通道

**设计语义**：内容流（RSS 新闻、社交更新），参与评分分类，走去重和 ACK。

**MCP tool 约定**：`get_proactive_events()` 返回 `list[dict]`，每个 dict 的 `kind` 为 `"content"`。

**标准 schema**（以 feed-mcp 为例）：

```json
{
  "event_id": "rss_abc123",
  "kind": "content",
  "source_type": "rss",
  "source_name": "HLTV.org",
  "title": "Vitality win BLAST Open Spring 2026",
  "content": "Vitality defeated NAVI 2-0...",
  "url": "https://www.hltv.org/news/40001/vitality-win-blast",
  "published_at": "2026-05-08T12:00:00",
  "display_text": "Vitality 2-0 NAVI · BLAST · 2026-05-08"
}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `event_id` | string | 是 | ACK 的唯一标识 |
| `kind` | string | 是 | 固定 `"content"` |
| `source_name` | string | 是 | 可读来源名 |
| `title` | string | 是 | 标题，agent 先看这个做初筛 |
| `url` | string | 是 | 原文链接，gateway 会据此预取正文 |
| `content` | string | 否 | 短摘要。详细正文由 gateway 通过 web_fetch 从 url 抓取 |
| `published_at` | string | 否 | ISO 时间戳 |
| `display_text` | string | 否 | 紧凑展示文本 |

**处理流程**：
1. gateway 调 `get_proactive_events` → 拿到 meta 列表
2. 并行 web_fetch 每个 `url` → 正文截断后存 content_store hashmap
3. agent 在 loop 中通过 `get_content` 工具按需取正文
4. 分类后 ACK 带 TTL

**Poll tool**（content 专用）：`poll_feeds()` — 后台周期性调用，让 MCP server 去真正抓取 RSS/API。

**真实实现**：`~/.shiori/workspace/mcp/feed-mcp/src/feed_backend.py:1284`：

```python
def get_proactive_events() -> list[dict[str, Any]]:
    rows = conn.execute("""
        SELECT i.event_id, i.source_type, i.source_name, i.title,
               i.content, i.url, i.published_at
        FROM items i LEFT JOIN acked_items a ON a.event_id = i.event_id
        WHERE a.event_id IS NULL
          AND coalesce(i.published_at, i.first_seen_at) >= ?
        ORDER BY coalesce(i.published_at, i.first_seen_at) DESC LIMIT ?
    """, (published_after, cfg.max_content_events)).fetchall()
    return [{
        "event_id": row["event_id"], "kind": "content",
        "source_type": row["source_type"], "source_name": row["source_name"],
        "title": row["title"], "content": row["content"],
        "url": row["url"], "published_at": row["published_at"],
        "display_text": _build_display_text(row),
    } for row in rows]
```

### 3. Context 通道

**设计语义**：背景上下文——不是事件流，不参与评分，不做 ACK。它作为背景块和 alert / content 一起放进本轮输入，帮 agent 判断时机和语气。

**与 alert/content 的根本不同**：
- 没有 event_id，不走去重，不做 ACK
- 不触发推送决策：只有 context、没有 alert / content 时，本轮照样按"没东西推"处理（走关系兜底或 drift）。以前的"只有 context 时按概率兜底推送"（`context_prob` / `context_only_daily_max`）已经移除

**MCP tool 约定**：每个 context 源定义独立 tool（命名习惯 `get_<name>_context`），返回单个 dict 或 list[dict]。没有强 schema 要求，只有语义约定：

```json
// fitbit sleep context
{
  "available": true,
  "summary": "用户当前可能已经睡着（概率 0.87），数据延迟约 5 分钟。",
  "sleep": {"state": "sleeping", "prob": 0.87, "prob_source": "hrv"}
}

// steam game context
{
  "available": true,
  "games": [{"name": "CS2", "recent_2w_hours": 12.5, "all_time_hours": 2340.0}],
  "realtime": {"online_status": "in-game", "currently_playing": "Counter-Strike 2"}
}
```

| 字段 | 说明 |
|------|------|
| `available` | 数据是否可用。false 时 agent 不应据此做推断 |
| `_source` | framework 自动注入，标记来自哪个 MCP server |
| `summary` / `hint` | 人类可读说明和判断指引 |

**真实实现**：
- fitbit sleep：`~/.shiori/workspace/mcp/fitbit-mcp/src/mcp_bridge.py:136`
- steam game：`~/.shiori/workspace/mcp/steam-mcp/steam_proactive.py`

---

## 一个完整的实际例子

以 fitbit 告警从数据源到用户收到消息的完整链路：

```
1. fitbit-mcp 后台运行，周期性拉 Fitbit API
   └── 检测到静息心率异常 → 写入内部事件队列

2. proactive loop tick
   └── DataGateway._fetch_alerts()
       └── pool.call("fitbit", "get_proactive_events", {})
       └── 返回 [{"event_id":"fb_001","kind":"alert","title":"hr_elevated_rest",...}]

3. agent loop（LLM 决策）
   └── system prompt："本轮如有 Alert → 整合所有 Alert → message_push → finish_turn"
   └── LLM 调 message_push: "你的静息心率在过去15分钟异常升高（92 bpm，基线68）。建议留意。"
   └── evidence: ["fitbit:fb_001"]
   └── finish_turn(decision=reply)

4. Post-loop → delivery 去重通过 → 消息语义去重通过 → Telegram 发送

5. ACK: acknowledge_events(event_ids=["fb_001"]) → fitbit-mcp 标记已处理
```
