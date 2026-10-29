"""An in-memory ``AFFECTION_HOST`` for the plugin's own tests.

The host's real implementation (role store, sessions, presence, the
user-only message rule) is tested in the host tree.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class FakeAffectionHost:
    """Roles, sessions and presence as plain dicts; ``completion`` is the model."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self.roles: dict[str, SimpleNamespace] = {}
        self.sessions: dict[str, SimpleNamespace] = {}
        self.user_at: dict[str, datetime] = {}
        self.proactive_at: dict[str, datetime] = {}
        self.stage_prompts: dict[str, dict[str, str]] = {}
        self.completion = ""
        self.saved: list[str] = []

    def add_role(self, role_id: str) -> None:
        self.roles[role_id] = SimpleNamespace(
            id=role_id, name=role_id.title(), description=""
        )

    @property
    def workspace(self) -> Path:
        return self._workspace

    def get_role(self, role_id: str) -> SimpleNamespace | None:
        return self.roles.get(role_id)

    def list_roles(self) -> Sequence[SimpleNamespace]:
        return list(self.roles.values())

    def role_session_key(self, role_id: str) -> str:
        return f"role:{role_id}"

    def get_session(self, session_key: str) -> SimpleNamespace:
        return self.sessions.setdefault(
            session_key, SimpleNamespace(key=session_key, metadata={}, messages=[])
        )

    async def save_session(self, session: Any) -> None:
        self.saved.append(session.key)

    def last_user_at(self, session_key: str) -> datetime | None:
        return self.user_at.get(session_key)

    def last_proactive_at(self, session_key: str) -> datetime | None:
        return self.proactive_at.get(session_key)

    def read_self(self, role_id: str) -> str:
        return ""

    def read_long_term(self, role_id: str) -> str:
        return ""

    def memory_is_template(self, text: str) -> bool:
        return not text

    def recent_user_messages(
        self, role_id: str, messages: list[Any]
    ) -> list[dict[str, str]]:
        return [
            {"role": item["role"], "content": item["content"]}
            for item in messages
            if item.get("role") in {"user", "assistant"}
        ]

    def stage_prompt_overrides(self, role_id: str) -> Mapping[str, str]:
        return dict(self.stage_prompts.get(role_id, {}))

    def update_stage_prompts(
        self,
        role_id: str,
        change: Callable[[Mapping[str, str]], Mapping[str, str]],
    ) -> None:
        self.stage_prompts[role_id] = dict(change(self.stage_prompt_overrides(role_id)))

    def compile_role_prompt(self, role_id: str) -> str:
        return f"you are {role_id}"

    async def complete(
        self,
        role_id: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None,
    ) -> str:
        return self.completion


@pytest.fixture
def host(tmp_path: Path) -> FakeAffectionHost:
    """A host with role ``mira``."""
    fake = FakeAffectionHost(tmp_path)
    fake.add_role("mira")
    return fake
