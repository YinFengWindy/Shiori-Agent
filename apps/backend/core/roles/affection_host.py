"""Host facts for the affection plugin.

The plugin keeps the relationship algorithms. Role records, sessions, presence,
memory documents and the dialogue model stay here. ``recent_user_messages``
keeps the "only the user's own messages" rule, because that rule lives in the
host's context scope.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from conversation.context_scope import belongs_to_user, load_user_context_threads
from core.memory.markdown import resolve_markdown_store
from core.memory.markdown_schema import DOCUMENT_DEFAULTS
from core.roles.role_prompt_compiler import RolePromptCompiler
from core.roles.self_seed_state import self_fingerprint
from core.roles.store import RoleStore
from proactive_v2.presence import PresenceStore
from session.manager import Session, SessionManager

from core.roles.role_runtime import RoleRuntimeRegistry

_RECENT_MESSAGE_LIMIT = 12
_RECENT_MESSAGE_CHAR_LIMIT = 6000
_TEMPLATE_MEMORY = self_fingerprint(DOCUMENT_DEFAULTS["MEMORY.md"])


class HostAffectionSources:
    """``AFFECTION_HOST`` over the owners this generation already has."""

    def __init__(
        self,
        *,
        workspace: Path,
        role_store: RoleStore,
        session_manager: SessionManager,
        presence: PresenceStore | None,
        role_runtime: RoleRuntimeRegistry | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._roles = role_store
        self._sessions = session_manager
        self._presence = presence
        self._role_runtime = role_runtime
        self._prompts = RolePromptCompiler()

    @property
    def workspace(self) -> Path:
        """The workspace. Affection files stay under ``roles/<id>/state``."""
        return self._workspace

    def get_role(self, role_id: str):
        """The persisted role, or ``None``."""
        return self._roles.get_role(role_id)

    def list_roles(self):
        """Every persisted role."""
        return self._roles.list_roles()

    def role_session_key(self, role_id: str) -> str:
        """The role's single session key."""
        return self._sessions.role_session_key(role_id)

    def get_session(self, session_key: str) -> Session:
        """The live session. Later mutations are visible to the caller."""
        return self._sessions.get_or_create(session_key)

    async def save_session(self, session: Session) -> None:
        """Persists the session the plugin just updated."""
        await self._sessions.save_async(session)

    def last_user_at(self, session_key: str) -> datetime | None:
        """Presence of the user's own last message."""
        if self._presence is None:
            return None
        return self._presence.get_last_user_at(session_key)

    def last_proactive_at(self, session_key: str) -> datetime | None:
        """Presence of the last proactive message."""
        if self._presence is None:
            return None
        return self._presence.get_last_proactive_at(session_key)

    def read_self(self, role_id: str) -> str:
        """Current SELF.md text."""
        return resolve_markdown_store(
            workspace=self._workspace, role_id=role_id
        ).read_self()

    def read_long_term(self, role_id: str) -> str:
        """Current MEMORY.md text."""
        return resolve_markdown_store(
            workspace=self._workspace, role_id=role_id
        ).read_long_term()

    def memory_is_template(self, text: str) -> bool:
        """Whether ``text`` is still the untouched MEMORY.md template."""
        return self_fingerprint(text) == _TEMPLATE_MEMORY

    def recent_user_messages(
        self, role_id: str, messages: list[Any]
    ) -> list[dict[str, str]]:
        """User-authored recent messages, newest window, oldest first."""
        threads = load_user_context_threads(self._workspace, role_id)
        pairs: list[dict[str, str]] = []
        total_chars = 0
        for message in reversed(messages):
            item = message if isinstance(message, dict) else {}
            role = str(item.get("role") or "").strip()
            if role not in {"user", "assistant"}:
                continue
            if not belongs_to_user(item, threads):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            total_chars += len(content)
            if total_chars > _RECENT_MESSAGE_CHAR_LIMIT and pairs:
                break
            pairs.append({"role": role, "content": content})
            if len(pairs) >= _RECENT_MESSAGE_LIMIT:
                break
        pairs.reverse()
        return pairs

    def stage_prompt_overrides(self, role_id: str) -> Mapping[str, str]:
        """The role's stage-guidance overrides. Missing role is an empty map."""
        role = self._roles.get_role(role_id)
        if role is None:
            return {}
        return dict(role.affection_stage_prompts)

    def update_stage_prompts(
        self,
        role_id: str,
        change: Callable[[Mapping[str, str]], Mapping[str, str]],
    ) -> None:
        """Applies ``change`` under the role lock."""

        def apply(current: dict[str, str]) -> dict[str, str]:
            return dict(change(current))

        self._roles.update_role(role_id, change_affection_stage_prompts=apply)

    def compile_role_prompt(self, role_id: str) -> str:
        """The compiled role definition the seed prompt quotes."""
        role = self._roles.get_role(role_id)
        if role is None:
            raise ValueError(f"role not found: {role_id}")
        return self._prompts.compile(role).content

    async def complete(
        self,
        role_id: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None,
    ) -> str:
        """One dialogue-model completion. Nested activate reuses the snapshot."""
        if self._role_runtime is None:
            raise RuntimeError("好感补全需要角色对话模型")
        runtime = await self._role_runtime.get(role_id)
        with runtime.activate_model("chat") as snapshot:
            response = await snapshot.provider.chat(
                messages=messages,
                tools=[],
                model=snapshot.model,
                max_tokens=max_tokens,
            )
        return str(response.content or "")
