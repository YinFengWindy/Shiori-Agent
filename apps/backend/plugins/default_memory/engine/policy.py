"""默认记忆引擎的记录转换与记忆域策略。"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict, cast

from core.memory.engine import MemoryMutation, MemoryQuery, MemoryRecord
from core.memory.utils import evidence_from_source_ref
from core.roles.policy import get_role_for_runtime_scope, is_shared_memory_enabled
from memory2.store import MemoryStore2


class _NormalizedIngestContent(TypedDict):
    user_message: str
    assistant_response: str
    tool_chain: list[dict[str, object]]
    source_ref: str


def _keep_count(window: int) -> int:
    aligned_window = max(6, ((max(1, window) + 5) // 6) * 6)
    return aligned_window // 2


class _PolicyMixin:
    """提供记录标准化、查询过滤与记忆域权限策略。"""

    def _require_v2_store(self) -> MemoryStore2:
        if self._v2_store is None:
            raise RuntimeError("memory v2 store unavailable")
        return self._v2_store

    @classmethod
    def _build_record(
        cls,
        item: dict[str, object],
        *,
        injected_ids: list[str] | None = None,
    ) -> MemoryRecord:
        extra = item.get("extra_json")
        signals = (
            dict(cast(dict[str, object], extra)) if isinstance(extra, dict) else {}
        )
        memory_kind = str(item.get("memory_type", "") or "")
        item_id = str(item.get("id", "") or "")
        source_ref = str(item.get("source_ref", "") or "")
        raw_score = item.get("score", 0.0)
        score = raw_score if isinstance(raw_score, int | float) else 0.0
        return MemoryRecord(
            id=item_id,
            kind=memory_kind,
            domain=str(item.get("memory_domain", "") or ""),
            summary=str(item.get("summary", "") or ""),
            score=float(score),
            engine_kind=cls.DESCRIPTOR.name,
            evidence=evidence_from_source_ref(source_ref),
            signals=signals,
            injected=item_id in set(injected_ids or []),
        )

    @staticmethod
    def _normalize_ingest_content(
        content: object,
    ) -> "_NormalizedIngestContent | None":
        if isinstance(content, dict):
            raw_tool_chain = content.get("tool_chain")
            normalized_tool_chain = (
                [item for item in raw_tool_chain if isinstance(item, dict)]
                if isinstance(raw_tool_chain, list)
                else []
            )
            return cast(
                _NormalizedIngestContent,
                {
                    "user_message": str(content.get("user_message", "") or ""),
                    "assistant_response": str(
                        content.get("assistant_response", "") or ""
                    ),
                    "tool_chain": normalized_tool_chain,
                    "source_ref": str(content.get("source_ref", "") or ""),
                },
            )
        if not isinstance(content, list):
            return None

        user_message = ""
        assistant_response = ""
        tool_chain: list[dict[str, object]] = []
        for message in content:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "") or "")
            body = str(message.get("content", "") or "")
            if role == "user" and body:
                user_message = body
            elif role == "assistant" and body:
                assistant_response = body
                maybe_tool_chain = message.get("tool_chain")
                if isinstance(maybe_tool_chain, list):
                    tool_chain = [
                        item for item in maybe_tool_chain if isinstance(item, dict)
                    ]
        if not user_message and not assistant_response:
            return None
        return cast(
            _NormalizedIngestContent,
            {
                "user_message": user_message,
                "assistant_response": assistant_response,
                "tool_chain": tool_chain,
                "source_ref": "",
            },
        )

    @staticmethod
    def _resolve_memory_types(
        request: MemoryQuery,
    ) -> list[str] | None:
        if request.filters.kinds:
            return [str(item) for item in request.filters.kinds if str(item).strip()]
        if request.intent == "procedure":
            return ["procedure", "preference"]
        return None

    @staticmethod
    def _resolve_memory_domains(
        request: MemoryQuery,
    ) -> list[str] | None:
        if request.filters.domains:
            return [str(item) for item in request.filters.domains if str(item).strip()]
        return None

    @staticmethod
    def _resolve_memory_domain_for_write(
        request: MemoryMutation,
        memory_type: str,
    ) -> str:
        explicit = str(request.memory_domain or "").strip()
        if explicit:
            return explicit
        if memory_type in {"identity", "background", "principle"}:
            return "role_self"
        if memory_type in {"profile", "preference", "procedure", "event"}:
            return "relationship"
        return ""

    def _guard_shared_memory_domains(
        self,
        memory_domains: list[str] | None,
        *,
        role_id: str,
    ) -> list[str] | None:
        if not memory_domains:
            return None
        allowed: list[str] = []
        for domain in memory_domains:
            clean_domain = str(domain).strip()
            if clean_domain != "shared":
                allowed.append(clean_domain)
                continue
            if self._is_memory_domain_allowed(clean_domain, role_id=role_id):
                allowed.append(clean_domain)
        return allowed or None

    def _is_domain_request_denied(
        self,
        requested_domains: list[str] | None,
        resolved_domains: list[str] | None,
    ) -> bool:
        """显式请求的记忆域若被权限裁掉，则本次查询应返回空结果而不是放宽过滤。"""

        requested = {
            str(item).strip() for item in requested_domains or [] if str(item).strip()
        }
        if not requested:
            return False
        resolved = {
            str(item).strip() for item in resolved_domains or [] if str(item).strip()
        }
        return not requested.issubset(resolved)

    def _ensure_memory_domain_allowed(
        self,
        memory_domain: str,
        *,
        role_id: str,
    ) -> None:
        clean_domain = str(memory_domain).strip()
        if not clean_domain:
            return
        if self._is_memory_domain_allowed(clean_domain, role_id=role_id):
            return
        raise ValueError(f"memory_domain 未授权: {clean_domain}")

    def _is_memory_domain_allowed(
        self,
        memory_domain: str,
        *,
        role_id: str,
    ) -> bool:
        clean_domain = str(memory_domain).strip()
        if clean_domain != "shared":
            return True
        role = get_role_for_runtime_scope(Path(self._workspace), role_id)
        return is_shared_memory_enabled(role)
