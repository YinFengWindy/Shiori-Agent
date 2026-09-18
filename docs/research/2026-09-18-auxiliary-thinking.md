# 辅助调用的 thinking 策略与实测（#310）

关联：[Issue #310](https://github.com/YinFengWindy/Shiori-Agent/issues/310)。
审计基线：`b9475cf800401ea12dd57c39472659c92efb1127`，2026-09-18。

## 结论与契约

允许辅助调用豁免角色 reasoning effort。调用方显式传
`call_purpose="auxiliary"`，由已有 provider strategy 处理关闭思考的协议。
不能简单让所有 `disable_thinking=True` 穿过角色代理：proactive/drift 的既有调用也传这个旧参数，
但它们在角色会话中承担角色发声，必须继续遵守角色 effort。

- 默认用途保留角色模型、effort、消息和流式行为；辅助用途仍使用同一个角色模型快照。
- DeepSeek 发送 `thinking.type=disabled` 并去掉 effort；DashScope/MiMo 发送 `enable_thinking=false`。
- 未识别的 OpenAI-compatible provider 只移除继承的 thinking 参数。没有通用的关闭协议，
  不能据此保证远端模型不推理，也不猜测它接受 `reasoning_effort=none`。
- 心情调用提供 `auxiliary_max_tokens=512`，在已知可关闭思考的 strategy 上使用
  `min(原预算, 512)`；未识别 strategy 保留调用方预算，避免把同一种截断问题带给其他模型。
- 其他摘要、压缩、检索假设、记忆标签/废弃判定和消息去重保留既有输出上限，只显式选择辅助用途。
- 不修改角色 effort 配置、正文纯文本契约、心情失败沿用上一轮状态的行为。

## 实际调用链审计

“处于角色会话”不等于“经过 RoleAwareProvider”。后者只包装 AgentLoop 的 LLMServices，
以及 proactive bootstrap 的 provider。ContextVar 不会让直连的 LLMProvider 自动变成代理。

| 显式关闭思考的路径（基线） | 当前默认接线 | #310 的实际影响与处理 |
| --- | --- | --- |
| `agent/core/reply_completion.fetch_role_mood` | `AgentLoop → DefaultReasoner → RoleAwareProvider` | **被覆盖**；正常正文后和角色阶段性正文后两个入口共享此函数，均改辅助用途 |
| `core/scene/decision.decide_scene` | `bootstrap/tools → SceneAwarenessController → 原始 light provider` | 默认接线未被覆盖；显式迁移辅助用途，也支持以后注入角色代理 |
| `core/memory/markdown/consolidation._call_llm_step` | `bootstrap/memory → worker → 原始 provider/light provider` | 默认接线未被覆盖；event extraction 和 recent context 共用此出口，均迁移 |
| `plugins/default_memory/backend/engine/lifecycle._extract_implicit_long_term` | 默认记忆引擎持有原始 provider | 默认接线未被覆盖；迁移辅助用途 |
| `plugins/story/backend/director.ProviderStoryDirector.generate` | `story/rpc._generate_turn → snapshot.provider` | 直接使用底层快照 provider，旧参数已经生效；迁移辅助用途，不改变正常 Story 生成策略 |
| `plugins/novelai/backend/scene_prompt.prepare_scene_prompt` | 插件 `ctx.light_provider`，来自原始 provider/light provider | 默认接线未被覆盖；迁移辅助用途 |
| `proactive_v2/agent_tick_factory._build_llm_fn`；`agent/core/drift_turn._execute_loop` | proactive 的 RoleAwareProvider，drift 通过前者调用 | 旧参数被覆盖属于角色策略；保留默认用途，不能当成辅助 JSON 调用一起关闭 |
| `memory2/query_rewriter.py` | 已在 #317 / #319 删除 | 当前没有调用路径 |

因此，当前确定因代理覆盖而增加推理的辅助源调用点为 **1 个共享函数、2 个心情调用入口**。
其余候选的原始 provider 路径没有这项“额外覆盖成本”，不能把下方强制代理回放的数字算作它们的生产成本。

Issue 评论提出的小预算路径另有两种情况：

| 小预算路径 | 核实结果 |
| --- | --- |
| passive `reasoning_result._summarize_incomplete_progress`，512 | 无 `reply_moods` 的小预算分支改为辅助；有角色心情的正式阶段性正文仍走整轮预算和角色 effort |
| `SubAgent._summarize_incomplete_progress` / `_force_final_summary`，各 512 | `SubagentManager` 直接传 `snapshot.provider`，没有代理覆盖，但旧调用确实未关闭继承的角色思考；两者改辅助用途 |
| recent context 512 / consolidation 1024 | 当前已经通过 `_call_llm_step` 传 `disable_thinking=True`，不是评论所述的完全未传；统一迁移该共享出口即可 |
| default memory `_gen_hypothesis`，80 | 活跃的内部检索调用，原先没有关闭思考；改辅助用途，避免极小预算只产出推理链 |
| `memory2/procedure_tagger.ProcedureTagger.tag`，128 | 原始 light provider 上的工具/技能标签 JSON，原先未关闭思考；改辅助用途 |
| `memory2/post_response_worker` 的 `_extract_invalidation_topics` / `_check_invalidate`，各 96 | 原始 light provider 上的废弃主题与候选条目判定，原先未关闭思考；两者改辅助用途 |
| `proactive_v2/judge.MessageDeduper.is_duplicate`，128 | proactive role tick 内经角色代理执行，只做重复消息校验、不生成角色正文；改辅助用途 |

`HistoryRoutePolicy` 与旧的 `proactive_v2/judge.Judge` 当前没有运行时构造调用；本次没有修改它们。
SELF.md 初始化、关系快照、屏幕视觉分析没有仅因输出结构化就被归入辅助用途。

## 实测方法

使用本机已经配置的 `deepseek-v4-flash` 服务，角色快照 effort 为 `high`，关闭客户端重试，
非流式调用，最多两个请求并发。使用合成输入，不读取或发送真实聊天、角色设定、记忆。
API 凭据仅在本地进程读取，没有写入报告或请求样本。

从基线 helper 捕获实际 messages / tools / tool_choice / response_format，固定请求后分别通过
基线和修复后的 `RoleAwareProvider` 回放；近期语境、隐式记忆和收尾使用同一源模块的 prompt builder / 常量。
全部回放明确激活角色 snapshot，验证高 effort 遇到这些预算时的行为，**不等同于所有生产入口都经过代理**。
心情对比 4096 → 512，其他预算不变；额外对心情做一次 512 → 512 的截断对照。

合成场景：澪听到“今天下雨了，但我终于修好了那个困扰很久的问题”，先回复撑伞、泡茶庆祝，
然后问心情；场景/Story 是粉发少女在雨夜车站等人；记忆输入为用户喜欢乌龙茶、希望推荐无糖饮料；
摘要输入为已修复空字符串解析错误但尚未运行回归测试；检索假设输入为“我喜欢哪种饮料？”。
标签输入为查询天气前先搜索当天预报；废弃判定为停用旧的浏览器搜索流程；去重输入为两条相同的下雨带伞提醒。
token 数使用服务端 `usage`，耗时为本地一次 provider 调用的 wall clock，不是端到端角色回合耗时。

## 实测结果

心情常规对照每侧 3 次，其他每侧 1 次。`输出 token` 为 completion_tokens，包含思考预算；
`旧推理 token` 来自服务端 reasoning_tokens。

| 请求 | 预算（前 → 后） | 旧推理 token | 输出 token（前 → 后） | 耗时秒（前 → 后） | 完成情况（前 → 后） |
| --- | --- | --- | --- | --- | --- |
| 心情，均值 | 4096 → 512 | 590（样本 827 / 556 / 387） | 631 → 35 | 3.116 → 1.274 | 3/3 JSON → 3/3 JSON |
| 心情，小预算对照 | 512 → 512 | 512 | 512 → 36 | 3.251 → 1.839 | length、空内容 → stop、有效 JSON |
| event extraction | 1024 → 1024 | 255 | 331 → 68 | 2.479 → 1.453 | stop → stop |
| recent context | 512 → 512 | 273 | 366 → 75 | 2.400 → 2.995 | stop → stop |
| 隐式长期记忆 | 600 → 600 | 600 | 600 → 87 | 4.082 → 1.768 | length、空内容 → stop、有效 JSON |
| Story（强制代理回放） | 1600 → 1600 | 770 | 1057 → 296 | 6.026 → 2.365 | stop → stop |
| 非角色阶段性摘要 | 512 → 512 | 512 | 512 → 289 | 3.517 → 3.643 | length、空内容 → stop、有内容 |
| 子 Agent 阶段性摘要 | 512 → 512 | 512 | 512 → 193 | 3.476 → 2.802 | length、空内容 → stop、有内容 |
| 子 Agent 最终摘要 | 512 → 512 | 512 | 512 → 266 | 3.839 → 7.591 | length、空内容 → stop、有内容 |
| 检索假设 | 80 → 80 | 80 | 80 → 5 | 1.064 → 1.318 | length、空内容 → stop、有内容 |
| procedure 标签 | 128 → 128 | 91 | 116 → 24 | 1.516 → 0.843 | stop → stop |
| 废弃主题提取 | 96 → 96 | 96 | 96 → 5 | 1.258 → 0.873 | length、空内容 → stop、有效 JSON |
| 废弃候选判定 | 96 → 96 | 67 | 76 → 8 | 1.240 → 0.667 | stop → stop |
| 主动消息去重 | 128 → 128 | 14 | 37 → 22 | 0.658 → 0.846 | stop → stop |
| 场景观察工具 | 600 → 600 | 无 usage | HTTP 400 → 143 | 0.408 → 1.382 | 拒绝 → 1 个 tool call |
| NovelAI 提示词工具 | 600 → 600 | 无 usage | HTTP 400 → 186 | 0.181 → 2.207 | 拒绝 → 1 个 tool call |

强制工具调用在旧代理回放下返回 `Thinking mode does not support this tool_choice`；另行复核两者得到相同错误。
这是代理覆盖的协议后果，不能据此宣称当前直连 light provider 的线上场景功能必然失败。

修复后的全部样本在 wire payload 中均为 `thinking.type=disabled`，没有 reasoning_effort，
响应没有 reasoning_content。服务端这时不返回 completion_tokens_details，因此不能把缺失的 reasoning_tokens
伪装成服务端明确报告的数字 0；能确认的是显式关闭参数生效、没有返回推理内容且可见输出恢复。

正常角色回合固定新增一次心情调用。在本组样本中，消除了平均 590 个 reasoning token，
completion token 平均少 596（94.5%），调用平均快 1.842 秒（59.1%）。
子 Agent 收尾和记忆压缩是条件触发，不能把表中所有行相加作为每轮节省。
样本较少、生成随机、网络与 prompt cache 状态不同；有些完整输出比旧空输出更慢，
因此这里只报告测得的差值，不承诺稳定延迟百分比，也不据此推断所有服务商行为。
