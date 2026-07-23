"""默认记忆引擎的写入与变更流程。"""

from __future__ import annotations

import logging
from typing import cast

from core.memory.engine import (
    MemoryIngestRequest,
    MemoryIngestResult,
    MemoryMutation,
    MemoryMutationResult,
    MemoryScope,
)
from core.memory.utils import resolve_memory_scope
from memory2.rule_schema import build_procedure_rule_schema

logger = logging.getLogger("plugins.default_memory.engine")


def _coerce_emotional_weight(value: object) -> int:
    if value is None or value == "":
        return 0
    if not isinstance(value, str | int | float):
        return 0
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return 0


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in value if isinstance(item, dict)]


def _item_matches_forget_scope(
    item: dict[str, object],
    scope: MemoryScope,
) -> bool:
    extra = item.get("extra_json")
    extra_json = cast(dict[str, object], extra) if isinstance(extra, dict) else {}
    if str(extra_json.get("role_id") or "").strip() != str(scope.role_id or "").strip():
        return False

    scope_channel = str(scope.channel or "").strip()
    scope_chat_id = str(scope.chat_id or "").strip()
    item_scope_channel = str(extra_json.get("scope_channel") or "").strip()
    item_scope_chat_id = str(extra_json.get("scope_chat_id") or "").strip()
    if not scope_channel or not scope_chat_id:
        return True
    if not item_scope_channel and not item_scope_chat_id:
        return True
    return item_scope_channel == scope_channel and item_scope_chat_id == scope_chat_id

def _coerce_memory_type(
    memory_type: str,
    tool_requirement: str | None,
    steps: list[str] | None,
) -> str:
    if memory_type != "procedure":
        return memory_type
    if tool_requirement and tool_requirement.strip():
        return memory_type
    if steps and any(str(step).strip() for step in steps):
        return memory_type
    return "preference"


def _split_write_result(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if ":" not in raw:
        return "new", raw
    status, item_id = raw.split(":", 1)
    return status or "new", item_id


def _dedupe_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        item_id = str(raw or "").strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    return out


class _MutationMixin:
    """提供 ingest、remember、forget 与长期记忆写入能力。"""

    async def ingest(self, request: MemoryIngestRequest) -> MemoryIngestResult:
        scope = resolve_memory_scope(request.scope)
        if self._post_response_worker is None:
            return MemoryIngestResult(
                accepted=False,
                summary="post_response_worker unavailable",
                raw={"reason": "worker_unavailable"},
            )
        if request.source_kind not in {"conversation_turn", "conversation_batch"}:
            return MemoryIngestResult(
                accepted=False,
                summary="unsupported source_kind",
                raw={"reason": "unsupported_source_kind"},
            )
        normalized = self._normalize_ingest_content(request.content)
        if normalized is None:
            return MemoryIngestResult(
                accepted=False,
                summary="unsupported content for conversation ingest",
                raw={"reason": "invalid_content"},
            )

        await self._post_response_worker.run(
            user_msg=normalized["user_message"],
            agent_response=normalized["assistant_response"],
            tool_chain=normalized["tool_chain"],
            source_ref=str(
                request.metadata.get("source_ref")
                or normalized["source_ref"]
                or f"{scope.session_key}@post_response"
            ),
            session_key=scope.session_key,
            channel=scope.channel,
            chat_id=scope.chat_id,
            role_id=scope.role_id,
        )
        return MemoryIngestResult(
            accepted=True,
            summary="delegated to post_response_worker",
            raw={"engine": self.DESCRIPTOR.name},
        )

    async def mutate(self, request: MemoryMutation) -> MemoryMutationResult:
        if request.kind == "forget":
            return await self._forget(request)
        return await self._remember(request)

    # 显式记忆写入入口，供 memorize 工具和内部迁移代码复用。
    async def _remember(self, request: MemoryMutation) -> MemoryMutationResult:
        # 1. procedure 必须有执行条件，否则降级为 preference。
        if self._memorizer is None:
            raise RuntimeError("memorizer unavailable")

        raw_steps = request.metadata.get("steps")
        steps = (
            [str(step) for step in cast(list[object], raw_steps)]
            if isinstance(raw_steps, list)
            else None
        )
        memory_type = _coerce_memory_type(
            request.memory_kind,
            str(request.metadata.get("tool_requirement") or ""),
            steps,
        )
        extra: dict[str, object] = {
            "tool_requirement": request.metadata.get("tool_requirement"),
            "steps": list(steps or []),
        }
        if request.scope.role_id:
            extra["role_id"] = request.scope.role_id
        memory_domain = self._resolve_memory_domain_for_write(request, memory_type)
        self._ensure_memory_domain_allowed(
            memory_domain,
            role_id=request.scope.role_id,
        )
        if memory_domain:
            extra["memory_domain"] = memory_domain
        if memory_type == "procedure":
            extra["rule_schema"] = build_procedure_rule_schema(
                summary=request.summary,
                tool_requirement=str(request.metadata.get("tool_requirement") or "")
                or None,
                steps=list(steps or []),
            )
            await self._attach_trigger_tags(extra=extra, summary=request.summary)

        # 2. 写入时顺带执行相似记忆 supersede，避免同类偏好堆积。
        result = await self._memorizer.save_item_with_supersede(
            summary=request.summary,
            memory_type=memory_type,
            extra=extra,
            source_ref=request.source_ref or "memorize_tool",
            happened_at=request.happened_at or None,
        )
        write_status, actual_id = _split_write_result(result)
        return MemoryMutationResult(
            accepted=bool(actual_id),
            item_id=actual_id,
            actual_kind=memory_type,
            status=write_status,
        )

    # 显式遗忘入口：只把条目标成 superseded，不物理删除。
    async def _forget(self, request: MemoryMutation) -> MemoryMutationResult:
        # 1. 先按 id 去重并读取现存条目。
        scope = resolve_memory_scope(request.scope)
        store = self._require_v2_store()
        clean_ids = _dedupe_ids(list(request.ids))
        items = [
            item
            for item in store.get_items_by_ids(clean_ids)
            if _item_matches_forget_scope(item, scope)
        ]
        found_ids = [str(item.get("id") or "") for item in items if item.get("id")]

        # 2. 只失效能确认存在的条目，缺失 id 返回给调用方展示。
        if found_ids:
            store.mark_superseded_batch(found_ids)
        return MemoryMutationResult(
            accepted=bool(found_ids),
            status="superseded",
            affected_ids=found_ids,
            missing_ids=[
                item_id for item_id in clean_ids if item_id not in set(found_ids)
            ],
            items=[
                {
                    "id": item.get("id"),
                    "memory_type": item.get("memory_type"),
                    "summary": item.get("summary"),
                }
                for item in items
            ],
        )

    async def _save_from_consolidation(
        self,
        history_entry: str,
        behavior_updates: list[dict[str, object]],
        source_ref: str,
        scope_channel: str,
        scope_chat_id: str,
        role_id: str = "",
        emotional_weight: int = 0,
    ) -> None:
        if self._memorizer is None:
            return
        await self._memorizer.save_from_consolidation(
            history_entry=history_entry,
            behavior_updates=behavior_updates,
            source_ref=source_ref,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            role_id=role_id,
            emotional_weight=emotional_weight,
        )

    async def _save_item_with_supersede(
        self,
        summary: str,
        memory_type: str,
        extra: dict[str, object],
        source_ref: str,
        happened_at: str | None = None,
        emotional_weight: int = 0,
    ) -> str:
        if self._memorizer is None:
            return ""
        return await self._memorizer.save_item_with_supersede(
            summary=summary,
            memory_type=memory_type,
            extra=extra,
            source_ref=source_ref,
            happened_at=happened_at,
            emotional_weight=emotional_weight,
        )

    async def _save_implicit_long_term(
        self,
        result: dict[str, object],
        *,
        source_ref: str,
        scope_channel: str,
        scope_chat_id: str,
        role_id: str = "",
    ) -> dict[str, int]:
        saved_counts = {"profile": 0, "preference": 0, "procedure": 0}

        # 1. profile 写入用户画像类事实。
        for item in _dict_items(result.get("profile")):
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            category = str(item.get("category") or "personal_fact").strip()
            raw_happened_at = item.get("happened_at")
            happened_at = raw_happened_at if isinstance(raw_happened_at, str) else None
            await self._save_item_with_supersede(
                summary=summary,
                memory_type="profile",
                extra={
                    "category": category,
                    "role_id": role_id,
                    "scope_channel": scope_channel,
                    "scope_chat_id": scope_chat_id,
                },
                source_ref=f"{source_ref}#profile",
                happened_at=happened_at,
                emotional_weight=_coerce_emotional_weight(item.get("emotional_weight")),
            )
            saved_counts["profile"] += 1
            logger.info("consolidation long_term saved: type=profile %r", summary[:60])

        # 2. preference / procedure 写入行为偏好和执行规则。
        for memory_type in ("preference", "procedure"):
            for item in _dict_items(result.get(memory_type)):
                summary = str(item.get("summary") or "").strip()
                if not summary:
                    continue
                extra: dict[str, object] = {
                    "tool_requirement": item.get("tool_requirement"),
                    "steps": item.get("steps") or [],
                    "role_id": role_id,
                    "scope_channel": scope_channel,
                    "scope_chat_id": scope_chat_id,
                }
                if memory_type == "procedure" and isinstance(
                    item.get("rule_schema"), dict
                ):
                    extra["rule_schema"] = item["rule_schema"]
                await self._save_item_with_supersede(
                    summary=summary,
                    memory_type=memory_type,
                    extra=extra,
                    source_ref=f"{source_ref}#implicit",
                    emotional_weight=_coerce_emotional_weight(
                        item.get("emotional_weight")
                    ),
                )
                saved_counts[memory_type] += 1
                logger.info(
                    "consolidation long_term saved: type=%s %r",
                    memory_type,
                    summary[:60],
                )
        return saved_counts
