"""Markdown memory 的 recent-context 渲染与 worker 能力。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from agent.llm_json import load_json_object_loose

from .contracts import _ConsolidationFailure, _ConsolidationWindow
from .formatting import (
    _is_context_frame_message,
    _is_memory_maintenance_assistant_message,
    _is_nsfw_memory_enabled_session,
    _normalize_memory_content,
    _parse_consolidation_payload,
)

if TYPE_CHECKING:
    from agent.provider import LLMProvider

logger = logging.getLogger("memory.markdown")

_RECENT_CONTEXT_TIMEOUT_S = 180.0

def _recent_turn_count(keep_count: int) -> int:
    return max(1, keep_count // 2)

def _message_time(message: dict) -> str:
    return str(message.get("timestamp") or "").strip()

def _format_recent_context_messages(
    messages: list[dict],
    *,
    nsfw_memory_enabled: bool = False,
) -> str:
    lines = []
    for message in messages:
        if _is_context_frame_message(message):
            continue
        content = _normalize_memory_content(
            message,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        role = str(message.get("role") or "").lower()
        if not content or role not in {"user", "assistant"}:
            continue
        if role == "assistant" and message.get("proactive"):
            continue
        if _is_memory_maintenance_assistant_message(message):
            continue
        if role == "assistant":
            preview = content[:60]
            if preview:
                lines.append(f"[a-preview] {preview}")
            continue
        lines.append(f"[user] {content}")
    return "\n".join(lines).strip()


def _replace_recent_turns_block(existing_text: str, recent_turns: str) -> str:
    block_lines = [
        "## Recent Turns",
        "<!-- a-preview = assistant reply preview only -->",
        recent_turns.strip() or "- none",
    ]
    block = "\n".join(block_lines).rstrip() + "\n"
    marker = "\n## Recent Turns\n"
    text = (existing_text or "").strip()
    if marker in text:
        prefix, _ = text.split(marker, 1)
        return prefix.rstrip() + "\n\n" + block
    if text:
        return text + "\n\n" + block
    return _render_recent_context(
        compression=None,
        compression_until="none",
        recent_turns=recent_turns,
    )


def _format_conversation_for_recent_context(
    messages: list[dict],
    *,
    nsfw_memory_enabled: bool = False,
) -> str:
    lines = []
    for message in messages:
        if _is_context_frame_message(message):
            continue
        content = _normalize_memory_content(
            message,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        role = str(message.get("role") or "").upper()
        if not content or role not in {"USER", "ASSISTANT"}:
            continue
        if role == "ASSISTANT" and message.get("proactive"):
            continue
        if _is_memory_maintenance_assistant_message(message):
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _render_recent_context(
    *,
    compression: dict[str, list[str]] | None,
    compression_until: str,
    recent_turns: str,
) -> str:
    compression = compression or {}
    ongoing_threads = [
        str(item).strip()
        for item in (compression.get("ongoing_threads") or [])
        if str(item).strip()
    ]
    sections = [
        ("最近持续关注", compression.get("active_topics") or []),
        ("最近明确偏好", compression.get("user_preferences") or []),
        ("最近待延续话题", compression.get("follow_ups") or []),
        ("最近避免事项", compression.get("avoidances") or []),
    ]
    lines = ["# Recent Context", "", "## Compression", f"until: {compression_until or 'none'}"]
    rendered_any = False
    for title, items in sections:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            continue
        rendered_any = True
        lines.append(f"- {title}：{'；'.join(cleaned[:3])}")
    if not rendered_any:
        lines.append("- none")
    lines.extend(["", "## Ongoing Threads"])
    if ongoing_threads:
        for item in ongoing_threads[:3]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "## Recent Turns", "<!-- a-preview = assistant reply preview only -->"])
    if recent_turns.strip():
        lines.append(recent_turns.strip())
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"

class _RecentContextWorkerMixin:
    @staticmethod
    def _build_recent_context_prompt(
        *,
        old_recent_context: str,
        conversation: str,
        recent_turns: str,
    ) -> str:
        return f"""你是近期语境压缩代理。你的任务不是自由总结，而是为后续 proactive 和 drift 保守地抽取近期语境。

目标：
1. 提取用户最近持续关注的话题
2. 提取最近新暴露、但尚未沉淀为长期记忆的显式偏好
3. 提取最近适合自然续接的话题
4. 提取最近应避免打扰、应避免推荐、或明显不想聊的方向
5. 提取跨窗口持续存在的重要现实线索（ongoing_threads）

规则：
- 只允许依据 USER 明确表达过的内容输出；ASSISTANT 的建议、解释、命名、延伸，一律不得当作证据
- recent_topics 可以总结“用户最近在讨论什么”，但必须贴近 USER 原话，不得升级成长期偏好
- active_topics 和 follow_ups 要优先写“话题层级”的概括，不要写 JSON Schema、函数名、字段名、具体术语翻译这类实现细节，除非用户明确把该细节当作核心关注点反复强调
- user_preferences 只允许在 USER 出现明确偏好/要求/禁忌表达时输出，例如：喜欢、偏好、希望、别、不要、避免、不想
- 不要把技术方案讨论、架构设想、问题求证、头脑风暴自动写成“用户偏好”
- 对技术讨论场景，只有当 USER 明确表达“以后都这样做 / 我就是偏好这种方式 / 我不要另一种方式 / 以后统一按这个来”时，才允许写 user_preferences；否则一律视为 active_topics 或 follow_ups
- 用户用“为什么不……”“能不能……”“是不是可以……”“只要不是最后一轮就……”这类方式提出方案设想或追问时，默认视为设计提议，不视为稳定偏好
- avoidances 只允许在 USER 明确表达“不要/别/避免/不想”时输出；没有明确否定表达就留空
- 如果最新 recent turns 显示话题已经明显切换，不要把较早窗口的技术讨论升级成当前偏好或避免事项
- 只保留未来几轮仍会影响主动行为的信息
- 不要记录工具细节、推理过程、普通寒暄
- 每个字段最多 3 条，每条尽量 1 句
- 没有把握就留空；宁可漏掉，也不要脑补

ongoing_threads 严格限制：
- 只记录用户正在经历、推进或承受的重要事情
- 必须是对用户当前生活、情绪、工作、学习、关系或健康有持续影响的线索
- 普通提问、技术讨论、方案脑暴、一次性 ask、知识求证，一律不得写入 ongoing_threads
- 若旧的 ongoing_threads 中已有某条重要线索，而当前窗口没有明确终结它，默认保留
- 只有当用户明确表示这件事已解决、结束、过去了、不再关心，才允许删除
- ongoing_threads 的写入门槛高于 active_topics；宁可少写，也不要把普通话题升级进去

专项禁令：
- 用户讨论“某个设计有没有依据/有没有实践/是否可行/为什么不这样做”，这是方案讨论，不是偏好；默认只能进入 active_topics 或 follow_ups，不能进入 user_preferences
- 用户说“为什么不让前台……只要不是最后一轮就……”是在提出一种实现设想，不等于“用户偏好以后统一这样做”
- 用户说“这样也不会引入额外延迟”“有没有这样的设计”，这是在分析方案目标，不等于稳定偏好
- 用户讨论“零延迟”“预加载”“流式预取”“前瞻性检索”这类设计目标时，默认视为当前方案讨论，不得直接提炼成 user_preferences
- 对方案讨论里的具体实现细节，优先上收一层概括，例如写“下一轮检索规划”“流式预取方案”，不要写“JSON Schema”“结构化预取指令”这类细碎实现点
- 用户说“睡觉了”“头有点疼”“身体不适”，这只是当前状态；除非用户明确说“别再聊这个”“不要继续”“我不想讨论”，否则不得生成 avoidances
- assistant 说“今晚先别想架构和代码了”“先休息”，这是 assistant 建议，不是用户 avoidances
- 如果较早窗口是技术方案讨论，而最新 recent turns 已切到睡眠/头痛/身体状态，则 user_preferences 和 avoidances 默认应为空；技术方案最多保留在 active_topics / follow_ups
- “最近在讨论前瞻性检索/流式预取方案”只能进入 active_topics / follow_ups，不能进入 ongoing_threads
- “用户最近几天反复因面试失败而情绪低落”“用户近期持续受睡眠紊乱影响”这类重要现实线索，才允许进入 ongoing_threads

反例：
- 错误：把“在 React 过程中同时输出下一轮检索内容”写成“用户偏好在对话中实时生成下一轮检索指令”
- 错误：把“这样也不会引入额外延迟”写成“用户偏好零延迟预加载”
- 错误：把“为什么不让前台在进行时同时输出自己想要什么”写成“用户偏好实时生成下一轮检索指令”
- 错误：把“睡觉了，吃了褪黑素头有点疼”写成“避免在身体不适时继续讨论技术架构”
- 错误：把“最近在讨论 React / 流式预取方案”写成 ongoing_threads
- 正确：active_topics 可写“用户最近在讨论前瞻性检索/流式预取方案”
- 正确：ongoing_threads 可写“用户最近几天反复提到面试受挫，持续影响情绪”
- 正确：如果用户没有明确说“希望/不要/避免/不想”，user_preferences 和 avoidances 可以为空

输出前自检：
1. 检查 user_preferences 中每一条，是否都能在 USER 原话里找到明确偏好/要求词（如“希望/不要/避免/不想/偏好/喜欢”）
2. 若找不到明确偏好/要求词，删除该条
3. 检查 avoidances 中每一条，是否都能在 USER 原话里找到明确否定/回避表达
4. 若找不到明确否定/回避表达，删除该条
5. 如果删除后为空，返回空数组，不要为了“信息完整”硬填

【上一版 recent context（仅供延续，不要机械复述）】
{old_recent_context or "（空）"}

【较早窗口（本次待压缩）】
{conversation or "（空）"}

【最新 recent turns（只用于判断是否已切话题，不可把 assistant 内容当证据）】
{recent_turns or "（空）"}

返回 JSON：
{{
  "active_topics": [],
  "user_preferences": [],
  "follow_ups": [],
  "avoidances": [],
  "ongoing_threads": []
}}
"""

    @staticmethod
    def _extract_recent_context_compression(text: str) -> dict[str, list[str]] | None:
        if not text.strip():
            return None
        section_match = re.search(
            r"## Compression\n(?P<body>.*?)(?:\n## Ongoing Threads\n|\Z)",
            text,
            flags=re.S,
        )
        if not section_match:
            return None
        body = section_match.group("body")
        parsed: dict[str, list[str]] = {
            "active_topics": [],
            "user_preferences": [],
            "follow_ups": [],
            "avoidances": [],
            "ongoing_threads": [],
        }
        title_map = {
            "最近持续关注": "active_topics",
            "最近明确偏好": "user_preferences",
            "最近待延续话题": "follow_ups",
            "最近避免事项": "avoidances",
        }
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("until:") or line == "- none":
                continue
            if not line.startswith("- "):
                continue
            payload = line[2:]
            if "：" not in payload:
                continue
            title, value = payload.split("：", 1)
            key = title_map.get(title.strip())
            if key is None:
                continue
            items = [part.strip() for part in value.split("；") if part.strip()]
            parsed[key] = items[:3]
        ongoing_match = re.search(
            r"## Ongoing Threads\n(?P<body>.*?)(?:\n## Recent Turns\n|\Z)",
            text,
            flags=re.S,
        )
        if ongoing_match:
            ongoing_items = []
            for raw_line in ongoing_match.group("body").splitlines():
                line = raw_line.strip()
                if line.startswith("- "):
                    item = line[2:].strip()
                    if item and item != "none":
                        ongoing_items.append(item)
            parsed["ongoing_threads"] = ongoing_items[:3]
        return parsed

    async def _build_recent_context_snapshot(
        self,
        *,
        session,
        profile_maint,
        window: _ConsolidationWindow | None,
        archive_all: bool,
        nsfw_memory_enabled: bool = False,
    ) -> str | _ConsolidationFailure:
        tail = list(session.messages[-self._keep_count :]) if self._keep_count > 0 else []
        recent_count = min(len(tail), _recent_turn_count(self._keep_count))
        session_messages = list(session.messages)
        if archive_all:
            compact_source = (
                session_messages[:-recent_count] if recent_count > 0 else session_messages
            )
        else:
            compact_source = list(window.old_messages) if window is not None else []
        compression_until = _message_time(compact_source[-1]) if compact_source else ""
        recent_turns = tail[-recent_count:] if recent_count > 0 else []
        rendered_recent_turns = _format_recent_context_messages(
            recent_turns,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        recent_turns_for_prompt = _format_conversation_for_recent_context(
            recent_turns,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        old_recent_context = ""
        if hasattr(profile_maint, "read_recent_context"):
            old_recent_context = str(
                await asyncio.to_thread(profile_maint.read_recent_context) or ""
        )
        conversation = _format_conversation_for_recent_context(
            compact_source,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        recent_context_provider, recent_context_model = (
            self._resolve_recent_context_llm(
                nsfw_memory_enabled=nsfw_memory_enabled,
            )
        )
        compression: dict[str, list[str]] | None = None
        if conversation:
            prompt = self._build_recent_context_prompt(
                old_recent_context=old_recent_context,
                conversation=conversation,
                recent_turns=recent_turns_for_prompt,
            )
            call_result = await self._call_llm_step(
                step="recent_context",
                provider=recent_context_provider,
                model=recent_context_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是近期语境压缩代理，只返回合法 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                timeout_s=_RECENT_CONTEXT_TIMEOUT_S,
            )
            if isinstance(call_result, _ConsolidationFailure):
                return call_result
            text, elapsed_ms = call_result
            logger.info(
                "Memory consolidation recent_context raw: elapsed_ms=%d chars=%d preview=%r",
                elapsed_ms,
                len(text),
                text[:300],
            )
            if not text:
                return _ConsolidationFailure(
                    step="recent_context",
                    error="empty_response",
                    elapsed_ms=elapsed_ms,
                )
            parsed = _parse_consolidation_payload(text)
            if isinstance(parsed, dict):
                compression = {
                    key: [
                        str(item).strip()
                        for item in (parsed.get(key) or [])
                        if str(item).strip()
                    ][:3]
                    for key in (
                        "active_topics",
                        "user_preferences",
                        "follow_ups",
                        "avoidances",
                        "ongoing_threads",
                    )
                }
            else:
                return _ConsolidationFailure(
                    step="recent_context",
                    error="invalid_json",
                    elapsed_ms=elapsed_ms,
                )
        elif old_recent_context.strip():
            compression = self._extract_recent_context_compression(old_recent_context)
        return _render_recent_context(
            compression=compression,
            compression_until=(
                compression_until
                or (
                    match.group(1).strip()
                    if old_recent_context.strip()
                    and (match := re.search(r"^until:\s*(.+)$", old_recent_context, flags=re.M))
                    else ""
                )
            ),
            recent_turns=rendered_recent_turns,
        )

    async def refresh_recent_turns(self, *, session, profile_maint=None) -> None:
        profile = profile_maint or self._profile_maint
        tail = list(session.messages[-self._keep_count :]) if self._keep_count > 0 else []
        recent_count = min(len(tail), _recent_turn_count(self._keep_count))
        recent_turns = tail[-recent_count:] if recent_count > 0 else []
        rendered_recent_turns = _format_recent_context_messages(
            recent_turns,
            nsfw_memory_enabled=_is_nsfw_memory_enabled_session(session),
        )
        existing_text = ""
        if hasattr(profile, "read_recent_context"):
            existing_text = str(await asyncio.to_thread(profile.read_recent_context) or "")
        updated = _replace_recent_turns_block(existing_text, rendered_recent_turns)
        if hasattr(profile, "write_recent_context"):
            await asyncio.to_thread(profile.write_recent_context, updated)
