"""Markdown memory 的 consolidation worker 与提取流程。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from core.memory.external_writes import ExternalLayerSnapshot
from core.memory.member_profiles import merge_member_profile

from .contracts import (
    ExternalLayerUpdates,
    _ConsolidationDraft,
    ConsolidationFailure,
)
from .formatting import (
    _budget_view,
    build_consolidation_source_ref,
    _coerce_history_text,
    _format_consolidation_error,
    format_conversation_for_consolidation,
    _format_pending_items,
    is_nsfw_memory_enabled_session,
    _normalize_history_entries,
    _parse_consolidation_payload,
    _select_consolidation_window,
    _select_recent_history_entries,
    _session_role_id,
    split_consolidation_window,
    _estimate_session_input_tokens,
)
from .external_segment import (
    GROUP_ENVIRONMENT_SYSTEM,
    ExternalThread,
    build_group_environment_prompt,
    format_external_thread,
    group_external_threads,
    member_batches,
    parse_group_environment_update,
    parse_member_profile_updates,
)
from .recent_context import _RecentContextWorkerMixin
from .user_layer import build_user_layer_prompt

if TYPE_CHECKING:
    from agent.provider import LLMProvider
    from conversation.context_scope import ContextView, UserContextThreads
    from core.identity import BoundUserSenders
    from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
    from core.memory.member_profiles import (
        MemberKey,
        MemberProfile,
        MemberProfileUpdate,
        MemberProfiles,
    )
    from .runtime import MarkdownMemoryStore

logger = logging.getLogger("memory.markdown")

_EVENT_EXTRACTION_TIMEOUT_S = 300.0
# 外部会话整理的输出预算：最近动态与群笔记，外加本批每个成员的档案与速记；
# 成员按 MEMBER_BATCH_SIZE 分批，单次调用至多 2048 + 400 × 8。
_GROUP_ENVIRONMENT_MAX_TOKENS = 2048
_MEMBER_PROFILE_MAX_TOKENS = 400
_CONSOLIDATION_SYSTEM = (
    "你是中性的 Markdown 记忆提取器，不扮演角色，也不生成用户可见回复。"
    "USER 是当前角色交流对象“你”，ASSISTANT 是当前角色“我”。"
    "自然语言输出必须使用“我 / 你 / 我们”。"
)


class _MarkdownConsolidationWorker(_RecentContextWorkerMixin):
    def __init__(
        self,
        *,
        profile_maint: "MarkdownMemoryStore",
        provider: "LLMProvider",
        model: str,
        keep_count: int,
        input_token_threshold: int = 75000,
        recent_context_provider: "LLMProvider | None" = None,
        recent_context_model: str | None = None,
    ) -> None:
        self._profile_maint = profile_maint
        self._provider = provider
        self._model = model
        self._recent_context_provider = recent_context_provider or provider
        self._recent_context_model = str(recent_context_model or "").strip() or model
        self._keep_count = keep_count
        self._consolidation_min_new_messages = max(5, keep_count // 2)
        self._input_token_threshold = max(0, int(input_token_threshold))

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
    ) -> tuple[str, int] | ConsolidationFailure:
        started_at = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                provider.chat(
                    messages=messages,
                    tools=[],
                    model=model,
                    max_tokens=max_tokens,
                    call_purpose="auxiliary",
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
            return ConsolidationFailure(step=step, error=error, elapsed_ms=elapsed_ms)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return (response.content or "").strip(), elapsed_ms

    async def extract_user_layer(
        self, conversation: str, profile_maint: "MarkdownMemoryStore"
    ) -> tuple[list[tuple[str, int]], str] | ConsolidationFailure:
        """把用户本人段 ``conversation`` 提取成 HISTORY 事件条目与 PENDING 候选。

        以 ``profile_maint`` 里现有的长期记忆查重、最近三条事件作主题参照。角色会话
        整理与旁听整理（#541）共用这一步。
        """
        current_memory = await asyncio.to_thread(profile_maint.read_long_term)
        history_text = ""
        if hasattr(profile_maint, "read_history"):
            history_text = _coerce_history_text(
                await asyncio.to_thread(profile_maint.read_history, 16000)
            )
        recent_history_block = "\n".join(
            f"- {entry}"
            for entry in _select_recent_history_entries(history_text, limit=3)
        )
        return await self._extract_user_layer(
            build_user_layer_prompt(current_memory, recent_history_block, conversation)
        )

    async def _extract_user_layer(
        self, prompt: str
    ) -> tuple[list[tuple[str, int]], str] | ConsolidationFailure:
        """调主模型提取用户层产物：HISTORY 事件条目与 PENDING 候选。"""
        call_result = await self._call_llm_step(
            step="event_extract",
            provider=self._provider,
            model=self._model,
            messages=[
                {"role": "system", "content": _CONSOLIDATION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
            timeout_s=_EVENT_EXTRACTION_TIMEOUT_S,
        )
        if isinstance(call_result, ConsolidationFailure):
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
            return ConsolidationFailure(
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
            return ConsolidationFailure(
                step="event_extract",
                error="invalid_json",
                elapsed_ms=event_elapsed_ms,
            )

        # 归一化文本产物，并把后续写入所需信息交给 engine。
        history_entry_payloads = _normalize_history_entries(
            result.get("history_entries"),
            result.get("history_entry"),
        )
        pending_items = _format_pending_items(result.get("pending_items", []))
        return history_entry_payloads, pending_items

    async def extract_external_layers(
        self,
        threads: list[ExternalThread],
        *,
        group_environment: "GroupEnvironment",
        member_profiles: "MemberProfiles",
        role_id: str,
        nsfw_memory_enabled: bool,
    ) -> ExternalLayerUpdates | ConsolidationFailure:
        """调主模型把外部段逐个会话整理成群环境层（#497）与成员层（#498）的更新。

        每个会话的成员按 ``MEMBER_BATCH_SIZE`` 分批，每批调用一次：第一批同时更新
        群环境，后续批次只产出成员档案，所以单次输出有上限。同一成员在本次窗口的
        多个会话里发言时，后面的调用看到的是前面合并后的档案。任一调用失败时语义与
        用户层整理一致：返回 ``ConsolidationFailure``，本次整理不提交、游标不推进，
        下次重试。
        """
        environment_updates: list[GroupEnvironmentUpdate] = []
        member_updates: list[MemberProfileUpdate] = []
        # 本次整理里已合并过的成员档案，尚未落盘；None 表示还没有档案。
        merged_members: dict[MemberKey, MemberProfile | None] = {}
        # 准备时读到的原始内容，提交时据此判断是否被别处（小手机）改过。
        read_members: dict[MemberKey, MemberProfile | None] = {}
        read_notes: dict[str, str] = {}
        for thread in threads:
            conversation = format_external_thread(
                thread, nsfw_memory_enabled=nsfw_memory_enabled
            )
            if not conversation:
                continue
            for index, batch in enumerate(member_batches(thread)):
                for sighting in batch:
                    if sighting.key not in merged_members:
                        profile = member_profiles.read(role_id, sighting.key)
                        merged_members[sighting.key] = profile
                        read_members[sighting.key] = profile
                with_environment = index == 0
                environment = (
                    group_environment.read(role_id, thread.thread_id)
                    if with_environment
                    else None
                )
                if environment is not None:
                    read_notes[thread.thread_id] = environment.group_note
                prompt = build_group_environment_prompt(
                    thread,
                    conversation,
                    environment,
                    batch,
                    {
                        sighting.key: profile
                        for sighting in batch
                        if (profile := merged_members[sighting.key]) is not None
                    },
                )
                payload = await self._call_external_layer_step(
                    prompt,
                    thread_id=thread.thread_id,
                    max_tokens=(
                        _GROUP_ENVIRONMENT_MAX_TOKENS if with_environment else 0
                    )
                    + _MEMBER_PROFILE_MAX_TOKENS * len(batch),
                )
                if isinstance(payload, ConsolidationFailure):
                    return payload
                if with_environment:
                    update = parse_group_environment_update(payload, thread)
                    if update.recent_activity or update.group_note:
                        environment_updates.append(update)
                for member_update in parse_member_profile_updates(
                    payload, thread, batch
                ):
                    member_updates.append(member_update)
                    merged_members[member_update.key] = merge_member_profile(
                        merged_members[member_update.key], member_update
                    )
        return ExternalLayerUpdates(
            group_environment=tuple(environment_updates),
            member_profiles=tuple(member_updates),
            snapshot=ExternalLayerSnapshot(
                group_notes={
                    update.thread_id: read_notes[update.thread_id]
                    for update in environment_updates
                    if update.group_note
                },
                member_profiles={
                    update.key: read_members[update.key] for update in member_updates
                },
            ),
        )

    async def _call_external_layer_step(
        self, prompt: str, *, thread_id: str, max_tokens: int
    ) -> dict | ConsolidationFailure:
        """外部段的一次整理调用，返回解析好的 JSON 对象；空回复或非法 JSON 即失败。"""
        call_result = await self._call_llm_step(
            step="group_environment_extract",
            provider=self._provider,
            model=self._model,
            messages=[
                {"role": "system", "content": GROUP_ENVIRONMENT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            timeout_s=_EVENT_EXTRACTION_TIMEOUT_S,
        )
        if isinstance(call_result, ConsolidationFailure):
            return call_result
        text, elapsed_ms = call_result
        payload = _parse_consolidation_payload(text) if text else None
        if payload is None:
            logger.warning(
                "Group environment consolidation: invalid response thread=%s %r",
                thread_id,
                text[:200],
            )
            return ConsolidationFailure(
                step="group_environment_extract",
                error="invalid_json" if text else "empty_response",
                elapsed_ms=elapsed_ms,
            )
        return payload

    async def prepare_consolidation(
        self,
        session,
        archive_all: bool = False,
        force: bool = False,
        input_token_estimate: int | None = None,
        user_threads: "UserContextThreads | None" = None,
        views: "tuple[ContextView, ...]" = (),
        *,
        group_environment: "GroupEnvironment",
        member_profiles: "MemberProfiles",
        bound_senders: "BoundUserSenders",
    ) -> _ConsolidationDraft | ConsolidationFailure | None:
        """准备一次整理：选窗口、拆段、提取用户层产物、整理外部段并生成 RECENT_CONTEXT。

        ``user_threads`` 是角色共享会话此刻的用户上下文会话；给出时窗口按发送者
        拆段，只有用户本人段进入用户层整理与引擎，RECENT_CONTEXT 只取用户上下文
        会话的消息。为 None 时会话没有划分，整个窗口都属于用户本人。外部段按会话
        整理成 ``group_environment`` 与 ``member_profiles`` 的更新；此刻身份绑定
        ``bound_senders`` 认出的用户本人不产生成员档案。``views`` 是本次推进游标的
        上下文（见 ``_select_consolidation_window``），非角色会话为空。
        """
        profile_maint = self._profile_maint
        # 1. 先决定这次要归档哪一段消息窗口；没有新窗口就直接返回。
        window = _select_consolidation_window(
            session,
            keep_count=self._keep_count,
            consolidation_min_new_messages=self._consolidation_min_new_messages,
            input_token_threshold=self._input_token_threshold,
            input_token_estimate=(
                _estimate_session_input_tokens(session, view=_budget_view(views))
                if input_token_estimate is None
                else input_token_estimate
            ),
            archive_all=archive_all,
            force=force,
            views=views,
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

        # 2. 窗口按发送者拆段：用户本人段格式化成对话文本，外部段在第 4 步按会话整理。
        nsfw_memory_enabled = is_nsfw_memory_enabled_session(session)
        segments = split_consolidation_window(window, user_threads)
        source_ref = build_consolidation_source_ref(segments.user_messages)
        conversation = format_conversation_for_consolidation(
            segments.user_messages,
            nsfw_memory_enabled=nsfw_memory_enabled,
            user_threads=user_threads,
        )
        scope_channel = getattr(session, "_channel", "")
        scope_chat_id = getattr(session, "_chat_id", "")

        # 3. 调主模型把用户本人段提炼成结构化结果；窗口里没有用户本人的发言时不调用。
        history_entry_payloads: list[tuple[str, int]] = []
        pending_items = ""
        if conversation:
            extracted = await self.extract_user_layer(conversation, profile_maint)
            if isinstance(extracted, ConsolidationFailure):
                return extracted
            history_entry_payloads, pending_items = extracted
        # 4. 外部段按会话整理成群环境层的最近动态与群笔记、成员层的成员档案；
        #    外部段为空时不调用。
        group_environment_updates: list[GroupEnvironmentUpdate] = []
        member_profile_updates: list[MemberProfileUpdate] = []
        external_snapshot = ExternalLayerSnapshot()
        external_threads = group_external_threads(window, segments, bound_senders)
        if external_threads:
            environment_result = await self.extract_external_layers(
                external_threads,
                group_environment=group_environment,
                member_profiles=member_profiles,
                role_id=_session_role_id(session),
                nsfw_memory_enabled=nsfw_memory_enabled,
            )
            if isinstance(environment_result, ConsolidationFailure):
                return environment_result
            group_environment_updates = list(environment_result.group_environment)
            member_profile_updates = list(environment_result.member_profiles)
            external_snapshot = environment_result.snapshot
        # 5. 归一化 markdown 产物，向量写入由 engine 订阅提交事件完成。
        recent_context_text = await self._build_recent_context_snapshot(
            session=session,
            profile_maint=profile_maint,
            window=window,
            archive_all=archive_all,
            nsfw_memory_enabled=nsfw_memory_enabled,
            user_threads=user_threads,
        )
        if isinstance(recent_context_text, ConsolidationFailure):
            return recent_context_text
        return _ConsolidationDraft(
            window=window,
            segments=segments,
            source_ref=source_ref,
            history_entry_payloads=history_entry_payloads,
            pending_items=pending_items,
            conversation=conversation,
            recent_context_text=recent_context_text,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            archive_all=archive_all,
            group_environment_updates=tuple(group_environment_updates),
            member_profile_updates=tuple(member_profile_updates),
            external_snapshot=external_snapshot,
        )
