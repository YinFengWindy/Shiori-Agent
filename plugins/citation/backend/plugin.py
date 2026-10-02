from __future__ import annotations

import json
import re
from typing import cast
from shiori_sdk import PluginRuntimeContext
from shiori_sdk.lifecycle import AfterReasoningCtx, LifecycleFrame

_REASONING_CTX_SLOT = "reasoning:ctx"
_PERSIST_CITED_SLOT = "persist:assistant:cited_memory_ids"
_TRAILING_PROTOCOL_TAG = r"<[a-zA-Z][a-zA-Z0-9_-]*:[^<>\s]+>"
_CITED_RE = re.compile(
    rf"(?:\n|\r\n)?§cited:\[([A-Za-z0-9_:,\-\s]*)\]§(?P<trailing>(?:\s*{_TRAILING_PROTOCOL_TAG}\s*)*)$",
    re.IGNORECASE,
)
_TRAILING_PROTOCOL_TAGS_RE = re.compile(
    rf"(?:\s*{_TRAILING_PROTOCOL_TAG}\s*)+$",
    re.IGNORECASE,
)
_INLINE_MEMORY_REF_RE = re.compile(
    r"[ \t]*(?:\[§[A-Za-z0-9:_-]{1,128}\])+", re.IGNORECASE
)


def _reasoning_ctx(frame: LifecycleFrame) -> AfterReasoningCtx:
    """Returns the reply gate context both modules require before they run.

    The host only runs these modules after ``after_reasoning.build_ctx`` has filled
    the slot, so anything else (including absence) is a wiring error, not a skip.
    """
    ctx = frame.slots.get(_REASONING_CTX_SLOT)
    if not isinstance(ctx, AfterReasoningCtx):
        raise TypeError(
            f"{_REASONING_CTX_SLOT} must hold AfterReasoningCtx, "
            f"got {type(ctx).__name__}"
        )
    return ctx


class CitationAfterReasoningModule:
    """Extracts citation metadata and removes citation markers from the reply."""

    slot = "citation.after_reasoning"
    requires = ("after_reasoning.build_ctx", _REASONING_CTX_SLOT)
    produces = (_REASONING_CTX_SLOT, _PERSIST_CITED_SLOT)

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        ctx = _reasoning_ctx(frame)
        reply = ctx.reply
        cleaned, cited_ids = extract_cited_ids(reply)
        cleaned = strip_inline_memory_refs(cleaned)
        if cited_ids:
            frame.slots[_PERSIST_CITED_SLOT] = cited_ids
        else:
            fallback_ids = extract_cited_ids_from_tool_chain(list(ctx.tool_chain))
            if fallback_ids:
                frame.slots[_PERSIST_CITED_SLOT] = fallback_ids
        if cleaned != reply:
            ctx.reply = cleaned
        return frame


class ProtocolTagCleanupModule:
    """Removes trailing protocol tags after other reply hooks have used them."""

    slot = "citation.protocol_cleanup"
    requires = ("after_reasoning.emit", _REASONING_CTX_SLOT)
    produces = (_REASONING_CTX_SLOT,)

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        ctx = _reasoning_ctx(frame)
        reply = ctx.reply
        cleaned = strip_inline_memory_refs(strip_trailing_protocol_tags(reply))
        if cleaned != reply:
            ctx.reply = cleaned
        return frame


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 citation：在回复后追踪记忆 ID，并清理遗留协议标签。"""
    ctx.lifecycle.contribute(
        "after_reasoning",
        [CitationAfterReasoningModule(), ProtocolTagCleanupModule()],
    )


def extract_cited_ids(response: str) -> tuple[str, list[str]]:
    """Returns display text and memory IDs from a valid trailing citation marker."""
    match = _CITED_RE.search(response)
    if not match:
        return response, []
    raw = match.group(1)
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    trailing = match.group("trailing").strip()
    clean = response[: match.start()].rstrip()
    if trailing:
        clean = f"{clean} {trailing}".strip()
    return clean, ids


def strip_trailing_protocol_tags(response: str) -> str:
    """Removes unused protocol tags only at the end of a reply."""
    return _TRAILING_PROTOCOL_TAGS_RE.sub("", response).rstrip()


def strip_inline_memory_refs(response: str) -> str:
    """Removes inline memory reference markers without deleting body text."""
    return _INLINE_MEMORY_REF_RE.sub("", response).rstrip()


def extract_cited_ids_from_tool_chain(
    tool_chain: list[dict[str, object]],
) -> list[str]:
    """Collects unique recall results in encounter order when the reply has no marker."""
    cited: list[str] = []
    seen: set[str] = set()
    for group in tool_chain:
        calls_value = group.get("calls")
        if not isinstance(calls_value, list):
            continue
        calls = cast(list[object], calls_value)
        for raw_call in calls:
            if not isinstance(raw_call, dict):
                continue
            call = cast(dict[str, object], raw_call)
            if str(call.get("name", "") or "") != "recall_memory":
                continue
            raw_result = str(call.get("result", "") or "").strip()
            if not raw_result:
                continue
            try:
                decoded = json.loads(raw_result)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(decoded, dict):
                continue
            data = cast(dict[str, object], decoded)
            raw_ids: list[object] = []
            cited_ids = data.get("cited_item_ids")
            if isinstance(cited_ids, list):
                raw_ids.extend(cast(list[object], cited_ids))
            else:
                items_value = data.get("items")
                if isinstance(items_value, list):
                    items = cast(list[object], items_value)
                    for raw_item in items:
                        if isinstance(raw_item, dict):
                            item = cast(dict[str, object], raw_item)
                            raw_ids.append(item.get("id"))
            for raw_id in raw_ids:
                item_id = str(raw_id or "").strip()
                if item_id and item_id not in seen:
                    seen.add(item_id)
                    cited.append(item_id)
    return cited
