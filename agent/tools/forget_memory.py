from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agent.tools.base import Tool
from core.memory.engine import MemoryMutation, MemoryScope, MemoryToolSpec

if TYPE_CHECKING:
    from core.memory.engine import MemoryWriteApi


class ForgetMemoryTool(Tool):
    name = "forget_memory"
    description = "由当前 memory engine 的 tool_profile 注入工具描述。"
    parameters = {
        "type": "object",
        "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["ids"],
    }

    def __init__(
        self,
        memory: "MemoryWriteApi",
        spec: MemoryToolSpec,
    ) -> None:
        self._memory = memory
        self._spec = spec
        self.description = self._spec.description
        self.parameters = self._spec.parameters

    async def execute(
        self,
        ids: list[str],
        role_id: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        **extra: Any,
    ) -> str:
        clean_ids = _clean_ids(ids)
        if not clean_ids:
            return _render_forget_result(clean_ids, [], [], [])

        result = await self._memory.mutate(
            MemoryMutation(
                kind="forget",
                ids=tuple(clean_ids),
                scope=MemoryScope(
                    role_id=str(role_id or "").strip(),
                    session_key=f"{channel}:{chat_id}" if channel and chat_id else "",
                    channel=channel or "",
                    chat_id=chat_id or "",
                ),
                metadata={
                    key: value
                    for key, value in extra.items()
                    if key in {"group_member_id", "group_id", "is_group_chat"}
                    and str(value or "").strip()
                },
            )
        )
        return _render_forget_result(
            clean_ids,
            result.affected_ids,
            result.missing_ids,
            result.items,
        )


def _clean_ids(ids: list[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        item_id = str(raw).strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            clean.append(item_id)
    return clean


def _render_forget_result(
    requested_ids: list[str],
    affected_ids: list[str],
    missing_ids: list[str],
    items: list[dict[str, object]],
) -> str:
    return json.dumps(
        {
            "requested_ids": requested_ids,
            "superseded_ids": affected_ids,
            "missing_ids": missing_ids,
            "count": len(affected_ids),
            "items": items,
        },
        ensure_ascii=False,
    )
