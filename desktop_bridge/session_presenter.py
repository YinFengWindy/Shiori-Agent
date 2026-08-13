from __future__ import annotations

from typing import Any

from desktop_bridge.tool_call_preview import truncate_desktop_tool_result
from session.manager import Session


class DesktopSessionPresenter:
    """Builds desktop session payloads from formal thread and runtime state."""

    def __init__(
        self,
        conversation_service,
        relationship_runtime: Any | None = None,
    ) -> None:
        self._conversation_service = conversation_service
        self._relationship_runtime = relationship_runtime

    def serialize(self, session: Session) -> dict[str, Any]:
        """Returns the desktop-compatible role session snapshot."""
        return {
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "metadata": self._enrich_metadata(dict(session.metadata)),
            "messages": [self._serialize_message(message) for message in session.messages],
        }

    def _enrich_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        if self._relationship_runtime is None:
            return metadata
        return self._relationship_runtime.enrich_session_metadata(metadata)

    @staticmethod
    def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
        metadata = message.get("metadata")
        merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        raw_turn_metrics = merged_metadata.get("turn_metrics")
        if isinstance(raw_turn_metrics, dict):
            turn_metrics = {
                key: value
                for key in ("total_tokens", "thinking_duration_ms")
                if isinstance((value := raw_turn_metrics.get(key)), int)
                and value >= 0
            }
            if turn_metrics:
                merged_metadata["turn_metrics"] = turn_metrics
            else:
                merged_metadata.pop("turn_metrics", None)
        skip_keys = {
            "id",
            "session_key",
            "seq",
            "role",
            "content",
            "timestamp",
            "reasoning_content",
            "tool_chain",
            "media",
            "metadata",
        }
        for key, value in message.items():
            if key not in skip_keys:
                merged_metadata[key] = value
        return {
            "id": message.get("id"),
            "role": message.get("role"),
            "content": message.get("content"),
            "timestamp": message.get("timestamp"),
            "reasoning_content": message.get("reasoning_content"),
            "tool_chain": DesktopSessionPresenter._sanitize_tool_chain(
                message.get("tool_chain")
            ),
            "media": list(message.get("media") or []),
            "metadata": merged_metadata,
        }

    @staticmethod
    def _sanitize_tool_chain(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        groups: list[dict[str, Any]] = []
        for raw_group in value:
            if not isinstance(raw_group, dict):
                continue
            calls: list[dict[str, Any]] = []
            for raw_call in raw_group.get("calls") or []:
                if not isinstance(raw_call, dict):
                    continue
                call_id = str(raw_call.get("call_id") or "").strip()
                tool_name = str(raw_call.get("name") or "").strip()
                if not call_id or not tool_name:
                    continue
                calls.append({
                    "call_id": call_id,
                    "name": tool_name,
                    "status": str(raw_call.get("status") or "success"),
                    "arguments": raw_call.get("arguments")
                    if isinstance(raw_call.get("arguments"), dict)
                    else {},
                    "final_arguments": raw_call.get("final_arguments")
                    if isinstance(raw_call.get("final_arguments"), dict)
                    else {},
                    "result": truncate_desktop_tool_result(
                        raw_call.get("result")
                    ),
                })
            if calls:
                groups.append({
                    "text": str(raw_group.get("text") or ""),
                    "reasoning_content": str(
                        raw_group.get("reasoning_content") or ""
                    ),
                    "calls": calls,
                })
        return groups
