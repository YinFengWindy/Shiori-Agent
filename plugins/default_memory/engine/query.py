"""默认记忆引擎的检索与问答流程。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import cast

from agent.provider import LLMResponse
from core.memory.engine import EngineProfile, MemoryQuery, MemoryQueryResult
from core.memory.utils import resolve_memory_scope, should_require_scope_match
from memory2.query_builder import build_procedure_queries

from .prompts import _explicit_hypothesis_prompt

logger = logging.getLogger("plugins.default_memory.engine")

_HYPOTHESIS_MAX_TOKENS = 80
_HYPOTHESIS_TIMEOUT_S = 3.0
_VECTOR_SCORE_THRESHOLD = 0.35
_VECTOR_TOP_K = 15
_ChatCall = Callable[..., Awaitable[LLMResponse]]


class _QueryMixin:
    """提供上下文、答案、时间线与兴趣检索能力。"""

    async def query(
        self,
        request: MemoryQuery,
    ) -> MemoryQueryResult:
        if self._retriever is None:
            return MemoryQueryResult(raw={"items": []})
        if request.intent == "timeline":
            return self._query_timeline(request)
        if request.intent == "interest":
            return await self._query_interest(request)
        if request.intent in {"context", "procedure"}:
            return await self._query_context(request)
        return await self._query_answer(request)

    async def _query_context(self, request: MemoryQuery) -> MemoryQueryResult:
        retriever = self._retriever
        if retriever is None:
            return MemoryQueryResult(raw={"items": []})
        scope = resolve_memory_scope(request.scope)
        queries = self._resolve_queries(request)
        memory_types = self._resolve_memory_types(request)
        requested_domains = self._resolve_memory_domains(request)
        memory_domains = self._guard_shared_memory_domains(
            requested_domains,
            role_id=scope.role_id,
        )
        if self._is_domain_request_denied(requested_domains, memory_domains):
            return MemoryQueryResult(
                records=[],
                trace={
                    "source": self.DESCRIPTOR.name,
                    "intent": request.intent,
                    "effect": request.effect,
                    "profile": EngineProfile.RICH_MEMORY_ENGINE.value,
                    "denied_domains": list(requested_domains),
                    "denied_reason": "memory_domain_unauthorized",
                },
                raw={"items": []},
            )
        items = await self._retrieve_related(
            request.text,
            memory_types=memory_types,
            memory_domains=memory_domains,
            top_k=request.limit,
            role_id=scope.role_id or None,
            scope_channel=scope.channel or None,
            scope_chat_id=scope.chat_id or None,
            require_scope_match=bool(
                request.filters.hints.get("require_scope_match", False)
            ),
            aux_queries=queries[1:],
            time_start=request.filters.time_start,
            time_end=request.filters.time_end,
        )
        text_block, injected_ids = retriever.build_injection_block(items)
        records = [
            self._build_record(item, injected_ids=injected_ids) for item in items
        ]
        return MemoryQueryResult(
            text_block=text_block,
            records=records,
            trace={
                "engine": self.DESCRIPTOR.name,
                "profile": self.DESCRIPTOR.profile.value,
                "intent": request.intent,
                "effect": request.effect,
            },
            raw={"items": items},
        )

    async def _query_answer(
        self,
        request: MemoryQuery,
    ) -> MemoryQueryResult:
        hyp1_task = asyncio.create_task(
            self._gen_hypothesis(request.text, style="event")
        )
        hyp2_task = asyncio.create_task(
            self._gen_hypothesis(request.text, style="general")
        )
        hyp1, hyp2 = await asyncio.gather(hyp1_task, hyp2_task)
        aux_queries = [text for text in (hyp1, hyp2) if text]
        scope = resolve_memory_scope(request.scope)
        types = self._resolve_memory_types(request)
        requested_domains = self._resolve_memory_domains(request)
        memory_domains = self._guard_shared_memory_domains(
            requested_domains,
            role_id=scope.role_id,
        )
        if self._is_domain_request_denied(requested_domains, memory_domains):
            return MemoryQueryResult(
                records=[],
                trace={
                    "source": self.DESCRIPTOR.name,
                    "intent": "answer",
                    "effect": request.effect,
                    "hit_count": 0,
                    "hyde_hypotheses": aux_queries,
                    "denied_domains": list(requested_domains or []),
                    "denied_reason": "memory_domain_unauthorized",
                },
                raw={"items": []},
            )
        hits = await self._retrieve_related(
            request.text,
            memory_types=types,
            memory_domains=memory_domains,
            top_k=max(request.limit, _VECTOR_TOP_K),
            role_id=scope.role_id or None,
            scope_channel=scope.channel or None,
            scope_chat_id=scope.chat_id or None,
            require_scope_match=should_require_scope_match(request, scope),
            aux_queries=aux_queries,
            score_threshold=_VECTOR_SCORE_THRESHOLD,
            time_start=request.filters.time_start,
            time_end=request.filters.time_end,
            keyword_enabled=True,
        )
        sliced = list(hits)[: request.limit]
        return MemoryQueryResult(
            records=[
                self._build_record(item) for item in sliced if isinstance(item, dict)
            ],
            trace={
                "source": self.DESCRIPTOR.name,
                "intent": request.intent,
                "effect": request.effect,
                "hit_count": len(sliced),
                "hyde_hypotheses": aux_queries,
            },
            raw={"items": sliced},
        )

    def _query_timeline(
        self,
        request: MemoryQuery,
    ) -> MemoryQueryResult:
        if request.filters.time_start is None or request.filters.time_end is None:
            return MemoryQueryResult(
                trace={
                    "source": self.DESCRIPTOR.name,
                    "intent": "timeline_missing_time",
                    "effect": request.effect,
                }
            )
        scope = resolve_memory_scope(request.scope)
        requested_domains = self._resolve_memory_domains(request)
        memory_domains = self._guard_shared_memory_domains(
            requested_domains,
            role_id=scope.role_id,
        )
        if self._is_domain_request_denied(requested_domains, memory_domains):
            return MemoryQueryResult(
                records=[],
                trace={
                    "source": self.DESCRIPTOR.name,
                    "intent": "timeline",
                    "effect": request.effect,
                    "hit_count": 0,
                    "denied_domains": list(requested_domains or []),
                    "denied_reason": "memory_domain_unauthorized",
                },
                raw={"items": []},
            )
        hits = self._require_v2_store().list_events_by_time_range(
            request.filters.time_start,
            request.filters.time_end,
            limit=request.limit,
            memory_domains=memory_domains,
            role_id=scope.role_id or None,
            scope_channel=scope.channel or None,
            scope_chat_id=scope.chat_id or None,
            require_scope_match=bool(
                str(scope.channel or "").strip() and str(scope.chat_id or "").strip()
            ),
        )
        return MemoryQueryResult(
            records=[
                self._build_record(item) for item in hits if isinstance(item, dict)
            ],
            trace={
                "source": self.DESCRIPTOR.name,
                "intent": "timeline",
                "effect": request.effect,
                "hit_count": len(hits),
            },
            raw={"items": list(hits)},
        )

    async def _query_interest(
        self,
        request: MemoryQuery,
    ) -> MemoryQueryResult:
        scope = resolve_memory_scope(request.scope)
        requested_domains = self._resolve_memory_domains(request)
        memory_domains = self._guard_shared_memory_domains(
            requested_domains,
            role_id=scope.role_id,
        )
        if self._is_domain_request_denied(requested_domains, memory_domains):
            return MemoryQueryResult(
                text_block="",
                records=[],
                trace={
                    "source": self.DESCRIPTOR.name,
                    "intent": "interest",
                    "effect": request.effect,
                    "denied_domains": list(requested_domains or []),
                    "denied_reason": "memory_domain_unauthorized",
                },
                raw={"items": []},
            )
        hits = await self._retrieve_related(
            request.text,
            memory_types=["preference", "profile"],
            memory_domains=memory_domains,
            top_k=request.limit,
            role_id=scope.role_id or None,
            scope_channel=scope.channel or None,
            scope_chat_id=scope.chat_id or None,
            require_scope_match=should_require_scope_match(request, scope),
        )
        records = [self._build_record(item) for item in hits if isinstance(item, dict)]
        texts = [record.summary for record in records]
        return MemoryQueryResult(
            text_block="\n---\n".join(texts),
            records=records,
            trace={
                "source": self.DESCRIPTOR.name,
                "intent": "interest",
                "effect": request.effect,
            },
            raw={"items": list(hits)},
        )

    async def _retrieve_related(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        top_k: int | None = None,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
        aux_queries: list[str] | None = None,
        score_threshold: float | None = None,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
        keyword_enabled: bool = True,
    ) -> list[dict[str, object]]:
        retriever = self._retriever
        if retriever is None:
            return []
        return cast(
            list[dict[str, object]],
            await retriever.retrieve(
                query,
                memory_types=memory_types,
                memory_domains=memory_domains,
                top_k=top_k,
                role_id=role_id,
                scope_channel=scope_channel,
                scope_chat_id=scope_chat_id,
                require_scope_match=require_scope_match,
                aux_queries=aux_queries,
                score_threshold=score_threshold,
                time_start=time_start,
                time_end=time_end,
                keyword_enabled=keyword_enabled,
            ),
        )

    async def _gen_hypothesis(self, query: str, style: str) -> str | None:
        prompt = _explicit_hypothesis_prompt(query, style)
        try:
            chat = cast(_ChatCall, getattr(self._light_provider, "chat"))
            resp = await asyncio.wait_for(
                chat(
                    messages=[{"role": "user", "content": prompt}],
                    tools=[],
                    model=self._light_model,
                    max_tokens=_HYPOTHESIS_MAX_TOKENS,
                ),
                timeout=_HYPOTHESIS_TIMEOUT_S,
            )
            text = (resp.content or "").strip()
            return text if text else None
        except Exception as e:
            logger.debug("explicit retrieval hypothesis failed: %s", e)
            return None

    async def _attach_trigger_tags(
        self,
        *,
        extra: dict[str, object],
        summary: str,
    ) -> None:
        if self._tagger is None:
            return
        try:
            trigger_tags = await self._tagger.tag(summary)
        except Exception:
            return
        if trigger_tags is not None:
            extra["trigger_tags"] = trigger_tags

    @staticmethod
    def _resolve_queries(request: MemoryQuery) -> list[str]:
        raw_queries = request.filters.hints.get("queries")
        if isinstance(raw_queries, list):
            queries = [str(item).strip() for item in raw_queries if str(item).strip()]
            if queries:
                return queries
        if request.intent == "procedure":
            return build_procedure_queries(request.text)
        return [request.text]
