"""Keep legacy role response envelopes out of dialogue and streaming consumers."""

from __future__ import annotations

import json
import re
from typing import Awaitable, Callable

_LEGACY_FIELDS = {"content", "mood", "thought"}


def normalize_role_content(content: str) -> str:
    """Decode only a complete legacy envelope; preserve all other text verbatim."""
    # Some copied model replies carry an HTML-encoded trailing space. Strip
    # only that suffix; decoding entities inside JSON would alter dialogue.
    candidate = re.sub(r"(?:&#x20;\s*)+$", "", content.strip(), flags=re.IGNORECASE)
    candidate = candidate.strip()
    lines = candidate.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in ("```json", "```")
        and lines[-1].strip() == "```"
    ):
        candidate = "\n".join(lines[1:-1]).strip()
    if not candidate.startswith("{") or not candidate.endswith("}"):
        return content
    try:
        # Retain pairs so duplicate keys cannot silently discard dialogue.
        fields = json.loads(candidate, object_pairs_hook=list)
    except json.JSONDecodeError:
        return content
    if (
        len(fields) != len(_LEGACY_FIELDS)
        or {key for key, _ in fields} != _LEGACY_FIELDS
        or any(not isinstance(value, str) for _, value in fields)
    ):
        return content
    return dict(fields)["content"]


class RoleReplyOutput:
    """Stream ordinary dialogue immediately and hold possible legacy envelopes.

    Only an opening object or code fence needs buffering until the provider's
    complete response can be classified. Thinking deltas always pass through.
    The provider already collects the response, so no second full buffer is kept.
    """

    def __init__(
        self,
        sink: Callable[[dict[str, str]], Awaitable[None]] | None,
        *,
        enabled: bool,
    ) -> None:
        self._sink = sink
        self._enabled = enabled
        self._prefix = ""
        self._buffering = False
        self._passthrough = False

    @property
    def callback(self):
        """Provide the adapted sink only for role calls with a live consumer."""
        return self._receive if self._enabled and self._sink else self._sink

    async def _receive(self, delta: dict[str, str]) -> None:
        assert self._sink is not None
        if self._passthrough:
            await self._sink(delta)
            return
        other = {key: value for key, value in delta.items() if key != "content_delta"}
        if other:
            await self._sink(other)
        content = delta.get("content_delta", "")
        if not content or self._buffering:
            return
        self._prefix += content
        start = self._prefix.lstrip()
        if not start or "```".startswith(start):
            return
        if start.startswith(("{", "```")):
            self._buffering = True
        else:
            self._passthrough = True
            await self._sink({"content_delta": self._prefix})
        self._prefix = ""

    async def finish(self, content: str | None) -> str | None:
        """Normalize final content and emit withheld dialogue exactly once."""
        if not self._enabled or content is None:
            return content
        normalized = normalize_role_content(content)
        if self._sink is not None and not self._passthrough and normalized:
            await self._sink({"content_delta": normalized})
        return normalized
