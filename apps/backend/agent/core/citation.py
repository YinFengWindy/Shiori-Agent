"""Memory citations in replies, owned by the core (D9).

The marker formats are the memory socket's (``shiori_sdk.memory.engine``), so
a reply is read and cleaned the same with any engine or none. Two steps:

- ``take_citations`` runs before the plugins' ``ReasoningFinished`` chain:
  it reads the trailing ``§cited:[...]§`` marker of each message (or, without
  one, the IDs ``recall_memory`` returned) and removes the markers. It must
  come first: a plugin resolving an emoji tag after the marker would leave it
  unmatched at the end of the reply.
- ``clean_reply`` is the fixed check after the chain (D11, §8.1): it removes
  trailing protocol tags no plugin consumed and inline ``[§id]`` references,
  including any a plugin wrote back. Markers elsewhere stay in the stored reply
  and are removed on delivery by ``strip_citation_markers``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import cast

from agent.tools.recall_memory import RecallMemoryTool
from shiori_sdk.core.conversation import ReasoningFinished
from shiori_sdk.kernel import Kernel
from shiori_sdk.memory.engine import (
    CITED_ITEM_IDS_KEY,
    CITED_MARKER_PATTERN,
    CITED_MARKER_STRIP_PATTERN,
    INLINE_MEMORY_REF_PATTERN,
)

# The tool whose results stand in for a missing citation marker.
RECALL_TOOL_NAME = RecallMemoryTool.name
_PROTOCOL_TAG = r"<[a-zA-Z][a-zA-Z0-9_-]*:[^<>\s]+>"
_TRAILING_CITED_RE = re.compile(
    rf"(?:\n|\r\n)?{CITED_MARKER_PATTERN}(?P<trailing>(?:\s*{_PROTOCOL_TAG}\s*)*)$",
    re.IGNORECASE,
)
_ANY_CITED_RE = re.compile(CITED_MARKER_STRIP_PATTERN)
_TRAILING_PROTOCOL_TAGS_RE = re.compile(rf"(?:\s*{_PROTOCOL_TAG}\s*)+$", re.IGNORECASE)
_INLINE_MEMORY_REF_RE = re.compile(
    rf"[ \t]*(?:{INLINE_MEMORY_REF_PATTERN})+", re.IGNORECASE
)


def extract_cited_ids(response: str) -> tuple[str, list[str]]:
    """``response`` without its trailing citation marker, and the marker's IDs.

    Protocol tags after the marker stay, so the plugins still see them.
    """
    match = _TRAILING_CITED_RE.search(response)
    if not match:
        return response, []
    ids = [item.strip() for item in match.group("ids").split(",") if item.strip()]
    trailing = match.group("trailing").strip()
    clean = response[: match.start()].rstrip()
    if trailing:
        clean = f"{clean} {trailing}".strip()
    return clean, ids


def strip_citation_markers(content: str) -> str:
    """``content`` without any citation marker, wherever it stands.

    It removes more than ``extract_cited_ids`` reads: a marker with malformed
    IDs must not reach the user either.
    """
    return _ANY_CITED_RE.sub(" ", content).strip()


def join_messages(messages: tuple[str, ...]) -> str:
    """The plain ``reply`` of a sequence reply: its messages, blank-line separated."""
    return "\n\n".join(messages)


def strip_inline_memory_refs(response: str) -> str:
    """Removes inline ``[§id]`` references without deleting body text."""
    return _INLINE_MEMORY_REF_RE.sub("", response).rstrip()


def strip_trailing_protocol_tags(response: str) -> str:
    """Removes the protocol tags left at the end of a reply."""
    return _TRAILING_PROTOCOL_TAGS_RE.sub("", response).rstrip()


def cited_ids_from_tool_chain(tool_chain: Iterable[Mapping[str, object]]) -> list[str]:
    """The IDs ``recall_memory`` returned this turn, unique, in encounter order.

    A result lists them under ``CITED_ITEM_IDS_KEY``, else as ``items[].id``;
    a result that is not a JSON object is skipped.
    """
    cited: list[str] = []
    for group in tool_chain:
        calls = group.get("calls")
        if not isinstance(calls, list):
            continue
        for call in cast(list[object], calls):
            if not isinstance(call, dict):
                continue
            call = cast(dict[str, object], call)
            if str(call.get("name", "") or "") != RECALL_TOOL_NAME:
                continue
            for item_id in _recalled_ids(str(call.get("result", "") or "").strip()):
                if item_id not in cited:
                    cited.append(item_id)
    return cited


def _recalled_ids(result: str) -> list[str]:
    if not result:
        return []
    try:
        decoded = json.loads(result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(decoded, dict):
        return []
    data = cast(dict[str, object], decoded)
    listed = data.get(CITED_ITEM_IDS_KEY)
    raw_ids: list[object] = []
    if isinstance(listed, list):
        raw_ids = cast(list[object], listed)
    elif isinstance(items := data.get("items"), list):
        raw_ids = [
            cast(dict[str, object], item).get("id")
            for item in cast(list[object], items)
            if isinstance(item, dict)
        ]
    return [item_id for raw in raw_ids if (item_id := str(raw or "").strip())]


def take_citations(
    messages: tuple[str, ...], tool_chain: Iterable[Mapping[str, object]]
) -> tuple[tuple[str, ...], list[str]]:
    """``messages`` without citation markers, and the turn's cited memory IDs.

    The IDs are those of every message's trailing marker, in order; when no
    message has one, those ``recall_memory`` returned. Inline ``[§id]``
    references are removed and never recorded.
    """
    cleaned: list[str] = []
    cited: list[str] = []
    for message in messages:
        text, found = extract_cited_ids(message)
        cleaned.append(strip_inline_memory_refs(text))
        cited.extend(found)
    return tuple(cleaned), cited or cited_ids_from_tool_chain(tool_chain)


def _clean(text: str) -> str:
    return strip_inline_memory_refs(strip_trailing_protocol_tags(text))


def clean_reply(event: ReasoningFinished) -> ReasoningFinished:
    """``event`` with every reply message cleaned of leftover markers.

    A sequence reply is cleaned message by message and ``reply`` stays their
    join; an event already clean is returned as it is.
    """
    if event.reply_messages:
        messages = tuple(_clean(message) for message in event.reply_messages)
        if messages == event.reply_messages:
            return event
        return replace(event, reply_messages=messages, reply=join_messages(messages))
    reply = _clean(event.reply)
    return event if reply == event.reply else replace(event, reply=reply)


def install_citation_checks(kernel: Kernel) -> None:
    """Adds ``clean_reply`` to ``kernel`` as the check after ``ReasoningFinished``."""

    async def check(event: ReasoningFinished) -> ReasoningFinished:
        return clean_reply(event)

    kernel.check(ReasoningFinished, check)
