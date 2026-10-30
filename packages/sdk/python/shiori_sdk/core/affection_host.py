"""``AFFECTION_HOST``: host facts the affection plugin cannot import (P6a).

The plugin keeps the relationship algorithms. Role records, sessions, presence,
memory documents and the dialogue model stay on the host. The host provides
this key before any plugin starts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from shiori_sdk.kernel import Key


class AffectionRole(Protocol):
    """The role fields relationship snapshots and seeds read."""

    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...


class AffectionSession(Protocol):
    """A live session the plugin reads; the plugin does not write it."""

    @property
    def key(self) -> str: ...

    @property
    def metadata(self) -> dict[str, Any]: ...

    @property
    def messages(self) -> list[Any]: ...


class AffectionHost(Protocol):
    """Host-owned inputs of one relationship runtime."""

    @property
    def workspace(self) -> Path:
        """The workspace. Affection files stay under ``roles/<id>/state``."""
        ...

    def get_role(self, role_id: str) -> AffectionRole | None: ...

    def list_roles(self) -> Sequence[AffectionRole]: ...

    def role_session_key(self, role_id: str) -> str: ...

    def get_session(self, session_key: str) -> AffectionSession: ...

    def last_user_at(self, session_key: str) -> datetime | None: ...

    def last_proactive_at(self, session_key: str) -> datetime | None: ...

    def read_self(self, role_id: str) -> str: ...

    def read_long_term(self, role_id: str) -> str: ...

    def memory_is_template(self, text: str) -> bool:
        """Whether ``text`` is still the untouched MEMORY.md template."""
        ...

    def recent_user_messages(
        self, role_id: str, messages: list[Any]
    ) -> list[dict[str, str]]:
        """User-authored recent messages. External speakers are already dropped."""
        ...

    def stage_prompt_overrides(self, role_id: str) -> Mapping[str, str]: ...

    def update_stage_prompts(
        self,
        role_id: str,
        change: Callable[[Mapping[str, str]], Mapping[str, str]],
    ) -> None:
        """Apply ``change`` under the role lock and persist the overrides."""
        ...

    def compile_role_prompt(self, role_id: str) -> str: ...

    async def complete(
        self,
        role_id: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None,
    ) -> str:
        """One dialogue-model completion. Empty content is an empty string."""
        ...


AFFECTION_HOST: Key[AffectionHost] = Key("affection_host")
"""Host facts for the affection plugin. The host provides this."""
