"""Markdown memory 的 consolidation worker 与提取流程。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .contracts import (
    _ConsolidationDraft,
    _ConsolidationFailure,
)
from .formatting import (
    _build_consolidation_source_ref,
    _coerce_history_text,
    _format_consolidation_error,
    _format_conversation_for_consolidation,
    _format_pending_items,
    _is_nsfw_memory_enabled_session,
    _normalize_history_entries,
    _parse_consolidation_payload,
    _select_consolidation_window,
    _select_recent_history_entries,
)
from .recent_context import _RecentContextWorkerMixin

if TYPE_CHECKING:
    from agent.provider import LLMProvider
    from .runtime import MarkdownMemoryStore

logger = logging.getLogger("memory.markdown")

_EVENT_EXTRACTION_TIMEOUT_S = 300.0

class _MarkdownConsolidationWorker(_RecentContextWorkerMixin):
    def __init__(
        self,
        *,
        profile_maint: "MarkdownMemoryStore",
        provider: "LLMProvider",
        model: str,
        keep_count: int,
        recent_context_provider: "LLMProvider | None" = None,
        recent_context_model: str | None = None,
    ) -> None:
        self._profile_maint = profile_maint
        self._provider = provider
        self._model = model
        self._recent_context_provider = recent_context_provider or provider
        self._recent_context_model = (
            str(recent_context_model or "").strip() or model
        )
        self._keep_count = keep_count
        self._consolidation_min_new_messages = max(5, keep_count // 2)

    def _resolve_recent_context_llm(
        self,
        *,
        nsfw_memory_enabled: bool,
    ) -> tuple["LLMProvider", str]:
        if nsfw_memory_enabled:
            return self._provider, self._model
        return self._recent_context_provider, self._recent_context_model

    async def _call_llm_step(
        self,
        *,
        step: str,
        provider: "LLMProvider",
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        timeout_s: float,
    ) -> tuple[str, int] | _ConsolidationFailure:
        started_at = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                provider.chat(
                    messages=messages,
                    tools=[],
                    model=model,
                    max_tokens=max_tokens,
                    disable_thinking=True,
                ),
                timeout=timeout_s,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            error = _format_consolidation_error(e)
            logger.error(
                "Memory consolidation llm step failed: step=%s elapsed_ms=%d error=%s",
                step,
                elapsed_ms,
                error,
            )
            return _ConsolidationFailure(step=step, error=error, elapsed_ms=elapsed_ms)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return (response.content or "").strip(), elapsed_ms

    async def prepare_consolidation(
        self,
        session,
        archive_all: bool = False,
        force: bool = False,
    ) -> _ConsolidationDraft | _ConsolidationFailure | None:
        profile_maint = self._profile_maint
        # 1. 先决定这次要归档哪一段消息窗口；没有新窗口就直接返回。
        window = _select_consolidation_window(
            session,
            keep_count=self._keep_count,
            consolidation_min_new_messages=self._consolidation_min_new_messages,
            archive_all=archive_all,
            force=force,
        )
        if archive_all:
            logger.info(
                "Memory consolidation (archive_all): %d total messages archived",
                len(session.messages),
            )
        else:
            if window is None:
                ready_count = (
                    len(session.messages) - self._keep_count - session.last_consolidated
                )
                if len(session.messages) <= self._keep_count:
                    logger.debug(
                        "Session %s: No consolidation needed (messages=%d, keep=%d)",
                        session.key,
                        len(session.messages),
                        self._keep_count,
                    )
                else:
                    logger.debug(
                        "Session %s: Not enough messages to consolidate yet (ready=%d, min=%d, last_consolidated=%d, total=%d)",
                        session.key,
                        ready_count,
                        self._consolidation_min_new_messages,
                        session.last_consolidated,
                        len(session.messages),
                    )
                return
            logger.info(
                "Memory consolidation started: %d total, %d new to consolidate, %d keep, force=%s",
                len(session.messages),
                len(window.old_messages),
                window.keep_count,
                force,
            )

        if window is None:
            return

        # 2. 把窗口消息格式化成一段对话文本，并准备好 source_ref / 现有长期记忆 / 最近 history。
        nsfw_memory_enabled = _is_nsfw_memory_enabled_session(session)
        source_ref = _build_consolidation_source_ref(window)
        conversation = _format_conversation_for_consolidation(
            window.old_messages,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        current_memory = await asyncio.to_thread(profile_maint.read_long_term)
        history_text = ""
        if hasattr(profile_maint, "read_history"):
            history_text = _coerce_history_text(
                await asyncio.to_thread(profile_maint.read_history, 16000)
            )
        recent_history_entries = _select_recent_history_entries(
            history_text,
            limit=3,
        )
        recent_history_block = "\n".join(
            f"- {entry}" for entry in recent_history_entries
        )

        scope_channel = getattr(session, "_channel", "")
        scope_chat_id = getattr(session, "_chat_id", "")

        prompt = f"""你是记忆提取代理（Memory Extraction Agent）。从对话中精确提取结构化信息，返回 JSON。

## 字段说明

### 1. "history_entries" → HISTORY.md（数组，每条对应一个独立主题）
按主题拆分，每个独立话题写一条对象，格式为 {{"summary":"...", "emotional_weight":0}}。
summary 仍然要求 1-2 句，以 [YYYY-MM-DD HH:MM] 开头，保留足够细节便于未来 grep 检索。
不同主题必须拆成独立条目，不得合并。若整段对话只有一个主题，返回只含一条的数组。

history_entries.emotional_weight 规则：
- 范围 0-10
- 普通技术讨论、普通事务记录、无明显情绪色彩 → 0
- 用户明确表达强烈喜欢/厌恶、明显受挫、关系冲突、情绪波动时按强度给 3-9
- 不确定时保守输出 0

**history_entries 提取规则（严格遵守）**：
1. 只提取 USER 明确表达的行动、经历、计划和状态；ASSISTANT 的建议、推荐、解释一律不写入，即使其中提到了地名、店名或活动。
2. 每条必须是简洁的第三人称摘要句，绝对不能包含 "USER:" 或 "ASSISTANT:" 等原始对话标记，不得复制粘贴原始对话文本。
3. 商家名称、地点、人名、数量、价格、型号等具体细节必须保留，不得用"某商店""某地方"概括。
4. 先判断当前 USER 内容的材料类型：是“用户此刻直接自述”，还是“用户正在展示一段外部聊天记录、截图 OCR、转贴 transcript 给助手看”。
5. 若 USER 内容属于外部聊天记录 / transcript，必须先做层级理解：
   - 外层：当前 USER 正在把一段材料发给助手看。
   - 内层：材料中可能有多个 speaker；这些 speaker 不自动等于当前 USER。
   - 只有当材料中某个 speaker 与当前 USER 的映射在当前会话里被明确确认时，才允许把该 speaker 的事实写入摘要。
6. 对 transcript 场景，默认认为 speaker 映射不明确；除非当前会话中有非常明确的显式说明，否则不要尝试判断材料里的某个昵称/说话人就是用户或对方。
7. 若 speaker 映射不明确，history_entries 只允许写 1 条高层 event，例如“用户向助手展示了一段与某人的聊天记录，内容涉及求职、学校、兴趣等话题”。
8. 对 transcript 场景，禁止输出任何未确认关系的句子，例如：
   - “用户向对方透露……”
   - “对方是……”
   - “双方确认……”
   - 把聊天记录里的具体事实直接写成用户个人经历
9. transcript 场景下，默认最多输出 1 条高层 history_entry；不要下钻成人物小传，不要替材料里的 speaker 自动补全身份关系，不要写任何昵称归属、学校归属、出生年份归属、爱好归属。

**transcript 场景示例（严格遵守）**：
- 错误：用户贴出一段聊天记录，speaker 归属未确认，却写成“用户向对方透露自己正在找暑期实习”。
- 错误：用户贴出一段聊天记录，直接写成“对方位于北京大兴区，就读于二外 MPAcc 专业”。
- 错误：用户贴出一段聊天记录，直接写成“对方昵称为‘一只快乐的小奶龙’”。
- 错误：用户贴出一段聊天记录，直接写成“用户曾为打 FGO 日服选修日语”。
- 正确：用户向助手展示了一段与匹配对象的聊天记录，聊天内容涉及学校背景、兴趣爱好和求职话题。

### 2. "pending_items" → PENDING.md 候选缓冲
只写用户的长期记忆候选，返回对象数组。每个对象格式：
{{"tag": "<tag>", "content": "<string>"}}

允许的 tag 只有 7 个：
- "identity"：稳定背景事实，如身份、学校/专业、长期技术方向、实习/工作经历、长期设备、长期维护项目
- "preference"：稳定偏好、禁忌、审美、游戏口味、价值取向
- "key_info"：用户明确允许保存的 key / token / id / 账号信息
- "health_long_term"：长期健康状态的一阶事实，只写长期状态，不写动态指标、基线、最近波动
- "requested_memory"：用户明确要求"长期记住"的关键内容，可比普通事实更连贯
- "correction"：对当前 MEMORY.md 现有事实的明确纠正
- "agent_context"：助手操作用户环境所需的工具性配置，如已部署服务的端口、环境变量名、工具分工约定、常用登录站点列表；不是用户画像，但对助手执行操作有长期价值；具体参数（端口号、变量名）必须完整保留。**硬规则：只有当对话明确表明该配置当前有效且助手已被授权使用时才提取；方案讨论、架构设计、网络诊断中出现的端口和地址一律不提取**

必须遵守：
- 只写跨对话仍有长期价值的内容
- 不写 agent 执行规则、SOP、工具调用顺序、流程规范
- 不写短期状态、近期计划、日程、课表、一次性操作
- 不写动态健康数据、实时指标、最近状态
- 不写对话过程总结
- 不写 self_insights、行为规律总结、关系演进感悟
- "requested_memory" 只能在用户明确表达"记住这个 / 写进长期记忆 / 以后要能聊到 / 希望你记住"时使用

进阶过滤（四条硬规则，任一触发即不提取）：

1. **网络运维细节不提取**
内网 IP、路由模式（如"CGNAT""桥接模式""NAT"）、运营商名称、MAC 地址等网络层配置属于瞬时运维信息，不提取。项目路径、配置文件名、环境变量名等与用户开发环境直接相关的信息可以提取。
✗ "家庭网络是联通宽带，光猫路由模式，内网 IP 192.168.1.x" → 不提取（网络层瞬时配置）
✓ "项目位于 /home/user/project，配置文件 config.toml" → 可提取（开发环境画像）

2. **临时状态不提取，规律习惯可提取**
带"最近""这周""目前""正在"等时间限定词的瞬时状态不提取。每周/每天持续的规律性行为模式可以提取为偏好或习惯标识。
✗ "用户最近加班频繁，靠咖啡撑着" → 不提取（瞬时状态，随时会变）
✓ "用户每周去健身房，主要做力量训练" → 可提取（规律性习惯，是长期生活方式）

3. **时效性数字和瞬时情绪不提取**
带有具体数值的动态指标（如 Star 数、增长率、评分）、瞬时情绪描述（如"失落""焦虑"）、正在进行中的短期状态。保留背后的价值判断，不提取数字和情绪本身。
✗ "项目刚突破 500 Star，但增速降到每天 2 个，用户为此很焦虑" → 不提取（数字过期、情绪瞬时）
✓ "用户长期维护某开源项目并重视社区增长" → 可提取（稳定身份信息）

4. **Agent 执行规则不放入 pending_items**
以"偏好"开头但语义上描述 agent 应如何执行的内容（如检索策略、元数据标注规范、输出格式要求等），属于 procedure，应由隐式提取路径写入向量库。
✗ "偏好搜索结果按来源可信度分层展示" → 不提取为 pending_item（agent 输出规范）
✗ "希望以后推荐前先查最新评测和社区反馈" → 不提取为 pending_item（agent 执行规则）

5. **agent_context 只提取已部署的配置，不提取方案讨论**
判断标准：对话中是否明确表明该服务/工具**当前已在运行**，且助手**已被告知可以使用**。
对话中提出的架构方案、网络诊断信息、假设性配置，即使出现了具体端口、地址或变量名，也不提取。

<example id="agent_context_proposal_vs_deployed">
反例（方案讨论 → 不提取）：
- 用户在讨论"可以搭一个 X 服务监听某端口"或"我们可以用 Y 工具穿透"——这是在设计方案，不是在告知助手已有的可用工具
- 用户问助手"这个配置怎么搭"——这是提问，不是已部署事实
- 对话中出现了 IP 地址或端口是为了排查问题、讲解原理——这是诊断/教学内容，不是可调用的配置

正例（已部署、已授权 → 提取）：
- 用户明确告知助手"X 服务现在跑着，你可以直接用"或"以后遇到 Y 场景就调这个接口"
- 用户描述了某个长期运行的工具，并期望助手在后续任务中利用它
</example>

若没有合格条目，返回空数组 []。

---

## 当前用户档案（用于查重）
{current_memory or "（空）"}

## 最近三次 consolidation event（仅用于主题延续参考）
使用原则（严格遵守）：
- 这些旧 event 只能帮助你理解“当前窗口大概在延续什么话题”，不能作为人物身份、说话人归属、关系判断或具体事实归属的直接证据。
- 若旧 event 与当前窗口原文在昵称、身份、关系、事实归属上存在冲突或不一致，必须以当前窗口原文为准。
- 不要因为旧 event 里出现了某个昵称、人设或关系描述，就在新的 history_entries 中继续沿用这些判断。
- 对 transcript / 聊天截图 / 转贴聊天场景，旧 event 绝不能用于推断“谁是当前用户、谁是对方、哪句话归谁”。
{recent_history_block or "（空）"},

## 待处理对话
{conversation}

只返回合法 JSON，不要 markdown 代码块。"""

        # 3. 调主模型把这段旧对话提炼成结构化结果。
        call_result = await self._call_llm_step(
            step="event_extract",
            provider=self._provider,
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            timeout_s=_EVENT_EXTRACTION_TIMEOUT_S,
        )
        if isinstance(call_result, _ConsolidationFailure):
            return call_result
        text, event_elapsed_ms = call_result
        logger.info(
            "Memory consolidation event llm raw: elapsed_ms=%d chars=%d preview=%r",
            event_elapsed_ms,
            len(text),
            text[:300],
        )

        if not text:
            logger.warning("Memory consolidation: LLM returned empty response")
            return _ConsolidationFailure(
                step="event_extract",
                error="empty_response",
                elapsed_ms=event_elapsed_ms,
            )
        result = _parse_consolidation_payload(text)
        if result is None:
            logger.warning(
                "Memory consolidation: unexpected response type. Response: %r",
                text[:200],
            )
            return _ConsolidationFailure(
                step="event_extract",
                error="invalid_json",
                elapsed_ms=event_elapsed_ms,
            )

        # 4. 归一化文本产物，并把后续写入所需信息交给 engine。
        history_entry_payloads = _normalize_history_entries(
            result.get("history_entries"),
            result.get("history_entry"),
        )
        pending_items = _format_pending_items(result.get("pending_items", []))
        # 4. 归一化 markdown 产物，向量写入由 engine 订阅提交事件完成。
        recent_context_text = await self._build_recent_context_snapshot(
            session=session,
            profile_maint=profile_maint,
            window=window,
            archive_all=archive_all,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        if isinstance(recent_context_text, _ConsolidationFailure):
            return recent_context_text
        return _ConsolidationDraft(
            window=window,
            source_ref=source_ref,
            history_entry_payloads=history_entry_payloads,
            pending_items=pending_items,
            conversation=conversation,
            recent_context_text=recent_context_text,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            archive_all=archive_all,
        )
