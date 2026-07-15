"""默认记忆引擎的初始化与生命周期接线。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from agent.config_models import Config
from agent.llm_json import load_json_object_loose
from agent.provider import LLMProvider
from agent.skills import SkillsLoader
from bus.events_lifecycle import TurnCommitted
from core.memory.engine import (
    EngineProfile,
    MemoryCapability,
    MemoryEngineDescriptor,
    MemoryToolProfile,
)
from core.memory.events import ConsolidationCommitted, TurnIngested
from core.net.http import SharedHttpResources
from memory2.embedder import Embedder
from memory2.memorizer import Memorizer
from memory2.post_response_worker import PostResponseMemoryWorker
from memory2.procedure_tagger import ProcedureTagger
from memory2.retriever import Retriever
from memory2.store import VEC_DIM, MemoryStore2
from plugins.default_memory.config import DefaultMemoryConfig, resolve_memory_db_path

from .admin import _AdminMixin
from .mutation import _MutationMixin
from .policy import _PolicyMixin
from .prompts import _build_long_term_prompt, _default_memory_tool_profile
from .query import _QueryMixin

if TYPE_CHECKING:
    from bus.event_bus import EventBus

logger = logging.getLogger("plugins.default_memory.engine")


def _build_entry_source_ref(base_source_ref: str, entry: str) -> str:
    text = (entry or "").strip()
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "empty"
    return f"{base_source_ref}#h:{digest}"


class DefaultMemoryEngine(
    _QueryMixin,
    _MutationMixin,
    _AdminMixin,
    _PolicyMixin,
):
    """默认的语义记忆引擎实现。"""

    DESCRIPTOR = MemoryEngineDescriptor(
        name="default",
        profile=EngineProfile.RICH_MEMORY_ENGINE,
        capabilities=frozenset(
            {
                MemoryCapability.INGEST_MESSAGES,
                MemoryCapability.RETRIEVE_SEMANTIC,
                MemoryCapability.RETRIEVE_CONTEXT_BLOCK,
                MemoryCapability.RETRIEVE_STRUCTURED_HITS,
                MemoryCapability.MANAGE_HISTORY,
                MemoryCapability.MANAGE_UPDATE,
                MemoryCapability.MANAGE_DELETE,
                MemoryCapability.SEMANTICS_RICH_MEMORY,
            }
        ),
        notes={"owner": "plugins.default_memory.engine"},
    )

    def __init__(
        self,
        *,
        config: Config,
        default_config: DefaultMemoryConfig,
        workspace: Path,
        provider: LLMProvider,
        light_provider: LLMProvider | None = None,
        http_resources: SharedHttpResources,
        event_publisher: "EventBus | None" = None,
    ) -> None:
        self._config = config
        self._default_config = default_config
        self._workspace = workspace
        self._provider = provider
        self._light_provider = light_provider or provider
        self._light_model = config.light_model or config.model
        self._v2_store: MemoryStore2 | None = None
        self._embedder: Embedder | None = None
        self._memorizer: Memorizer | None = None
        self._retriever: Retriever | None = None
        self._tagger: ProcedureTagger | None = None
        self._post_response_worker: PostResponseMemoryWorker | None = None
        self._event_bus = event_publisher
        self.closeables: list[object] = []

        db_path = resolve_memory_db_path(
            workspace=workspace,
            default_config=default_config,
        )
        embedding = config.memory.embedding
        retrieval = default_config.retrieval
        self._v2_store = MemoryStore2(
            db_path,
            vec_dim=embedding.output_dimensionality or VEC_DIM,
        )
        self._embedder = Embedder(
            base_url=embedding.base_url
            or config.light_base_url
            or config.base_url
            or "",
            api_key=embedding.api_key or config.light_api_key or config.api_key,
            model=embedding.model,
            output_dimensionality=embedding.output_dimensionality,
            requester=http_resources.external_default,
        )
        self._memorizer = Memorizer(self._v2_store, self._embedder)
        self._retriever = Retriever(
            self._v2_store,
            self._embedder,
            top_k=retrieval.top_k_history,
            score_threshold=retrieval.score_threshold,
            score_thresholds={
                "procedure": retrieval.thresholds.procedure,
                "preference": retrieval.thresholds.preference,
                "event": retrieval.thresholds.event,
                "profile": retrieval.thresholds.profile,
            },
            relative_delta=retrieval.relative_delta,
            inject_max_chars=retrieval.inject.max_chars,
            inject_max_forced=retrieval.inject.forced,
            inject_max_procedure_preference=retrieval.inject.procedure_preference,
            inject_max_event_profile=retrieval.inject.event_profile,
            inject_line_max=retrieval.inject.line_max,
            procedure_guard_enabled=retrieval.procedure_guard_enabled,
            hotness_alpha=0.20,
        )
        skills_loader = SkillsLoader(workspace)
        self._tagger = ProcedureTagger(
            provider=self._light_provider,
            model=self._light_model,
            skills_fn=lambda: [
                s["name"] for s in skills_loader.list_skills(filter_unavailable=False)
            ],
        )
        self._post_response_worker = PostResponseMemoryWorker(
            memorizer=self._memorizer,
            retriever=self._retriever,
            light_provider=self._light_provider,
            light_model=self._light_model,
            event_publisher=event_publisher,
        )
        self._wire_memory2_events()
        self.closeables = [self._v2_store, self._embedder]

    @classmethod
    def ensure_workspace_storage(
        cls,
        *,
        default_config: DefaultMemoryConfig,
        workspace: Path,
    ) -> None:
        db_path = resolve_memory_db_path(
            workspace=workspace,
            default_config=default_config,
        )
        store = MemoryStore2(db_path)
        store.close()

    def _wire_memory2_events(self) -> None:
        if self._event_bus is None:
            return
        if self._post_response_worker is not None:
            self._event_bus.on(TurnCommitted, self._on_turn_committed)
            self._event_bus.on(TurnIngested, self._post_response_worker.handle)
        if self._memorizer is not None:
            self._event_bus.on(ConsolidationCommitted, self._on_consolidation_committed)

    # 对话提交后只入队，不在主回复链路里等待 memory2 后处理。
    def _on_turn_committed(self, event: TurnCommitted) -> None:
        if bool((event.extra or {}).get("skip_post_memory")):
            return
        if self._event_bus is None:
            return
        source_ref = f"{event.session_key}@post_response"
        self._event_bus.enqueue(
            TurnIngested(
                session_key=event.session_key,
                channel=event.channel,
                chat_id=event.chat_id,
                user_message=event.input_message,
                assistant_response=event.assistant_response,
                tool_chain=cast(list[dict[str, object]], event.tool_chain_raw),
                source_ref=source_ref,
                role_id=event.role_id,
            )
        )

    async def _on_consolidation_committed(
        self,
        event: ConsolidationCommitted,
    ) -> None:
        save_coros = [
            self._save_from_consolidation(
                history_entry=entry,
                behavior_updates=[],
                source_ref=_build_entry_source_ref(event.source_ref, entry),
                scope_channel=event.scope_channel,
                scope_chat_id=event.scope_chat_id,
                role_id=event.role_id,
                emotional_weight=emotional_weight,
            )
            for entry, emotional_weight in event.history_entry_payloads
        ]
        if save_coros:
            await asyncio.gather(*save_coros)
        implicit_result = await self._extract_implicit_long_term(
            conversation=event.conversation,
            existing_profile="",
        )
        if implicit_result:
            await self._save_implicit_long_term(
                implicit_result,
                source_ref=event.source_ref,
                scope_channel=event.scope_channel,
                scope_chat_id=event.scope_chat_id,
                role_id=event.role_id,
            )

    async def _extract_implicit_long_term(
        self,
        *,
        conversation: str,
        existing_profile: str = "",
    ) -> dict[str, object] | None:
        try:
            started_at = time.perf_counter()
            prompt = _build_long_term_prompt(
                conversation=conversation,
                existing_profile=existing_profile,
            )
            resp = await self._provider.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                model=self._config.model,
                max_tokens=600,
                disable_thinking=True,
            )
            text = (resp.content or "").strip()
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "Memory consolidation implicit llm raw: elapsed_ms=%d chars=%d preview=%r",
                elapsed_ms,
                len(text),
                text[:300],
            )
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = load_json_object_loose(text)
            if not isinstance(result, dict):
                raise RuntimeError("long_term extraction returned non-object JSON")
            return result
        except Exception as e:
            logger.warning("consolidation long_term extraction failed: %s", e)
            raise RuntimeError("consolidation long_term extraction failed") from e

    def tool_profile(self) -> MemoryToolProfile:
        return _default_memory_tool_profile()

    def describe(self) -> MemoryEngineDescriptor:
        return self.DESCRIPTOR
