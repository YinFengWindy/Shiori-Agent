"""An in-memory ``MARKDOWN_MEMORY`` and model fixtures for the plugin's own tests.

The host's real port (role directories, document schema, role state) is
tested in the host tree.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from shiori_sdk.testing.models import FakeModelResponse


@dataclass
class FakeRoleDocuments:
    """One role's documents; ``commits`` / ``rollbacks`` count the merge outcomes."""

    long_term: str = ""
    self_text: str = ""
    pending: str = ""
    snapshot: str | None = None
    history: list[str] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)
    seed_pending: bool = False
    backups: int = 0
    commits: int = 0
    rollbacks: int = 0

    def read_long_term(self) -> str:
        return self.long_term

    def read_self(self) -> str:
        return self.self_text

    def write_self(self, content: str) -> None:
        self.self_text = content

    def self_seed_pending(self) -> bool:
        return self.seed_pending

    def snapshot_pending(self) -> str:
        self.rollback_pending_snapshot()
        if not self.pending:
            return ""
        self.snapshot, self.pending = self.pending, ""
        return self.snapshot

    def commit_long_term(self, content: str, *, history_entry: str) -> None:
        if self.long_term.strip():
            self.backups += 1
        self.long_term = content
        if history_entry:
            self.history.append(history_entry)
        self.snapshot = None
        self.commits += 1

    def rollback_pending_snapshot(self) -> None:
        if self.snapshot is None:
            return
        self.pending = "\n".join(part for part in (self.snapshot, self.pending) if part)
        self.snapshot = None
        self.rollbacks += 1

    def read_state(self) -> Mapping[str, object]:
        return dict(self.state)

    def write_state(self, key: str, value: object) -> None:
        self.state[key] = value


class FakeMarkdownMemory:
    """Roles' documents keyed by role id; an unknown role does not exist."""

    default_self = "# 我是谁\n\n## 我的性格与形象\n- 默认\n"

    def __init__(self) -> None:
        self.roles: dict[str, FakeRoleDocuments] = {}

    def role(self, role_id: str) -> FakeRoleDocuments | None:
        return self.roles.get(role_id)


class HeldProvider:
    """Answers each chat in order; ``hold`` keeps the next chat waiting until set."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.requests: list[str] = []
        self.hold: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.cancelled = False

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        model: str,
        max_tokens: int | None,
        *,
        call_purpose: Literal["default", "auxiliary"] = "default",
        tool_choice: str | dict[str, object] = "auto",
        payload_snapshot_enabled: bool | None = None,
    ) -> FakeModelResponse:
        self.requests.append(model)
        self.started.set()
        if self.hold is not None:
            try:
                await self.hold.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if not self.replies:
            raise AssertionError("unexpected chat request")
        return FakeModelResponse(content=self.replies.pop(0))


@dataclass(frozen=True)
class Snapshot:
    """A role's activated chat model."""

    provider: HeldProvider
    model: str
