"""Initializes SELF once inside the existing role conversation lock."""

from __future__ import annotations

from core.roles.errors import RoleNotFoundError

import asyncio
from typing import TYPE_CHECKING, Any

from core.memory.markdown_schema import normalize_memory_document

from .memory_service import RoleMemoryService
from .model_runtime import RoleModelSnapshot
from shiori_sdk.values import now_iso
from .self_seed import LlmRoleSelfSeedGenerator
from .self_seed_state import resolve_self_seed_state, self_fingerprint
from .store import RoleStore

if TYPE_CHECKING:
    from .models import RoleRecord
    from .relationship_runtime.affection_seed import RoleAffectionInitializer


class SelfInitializationError(RuntimeError):
    """A failed seed stops this turn while preserving the role for a later retry."""


class RoleSelfInitializer:
    """Owns seed state, edit protection and persistence; callers hold the role turn lock.

    Once SELF.md is ready, the same flow seeds the role's initial affection.
    """

    def __init__(
        self,
        store: RoleStore,
        generator: LlmRoleSelfSeedGenerator,
        affection: RoleAffectionInitializer,
    ):
        self._store = store
        self._memory = RoleMemoryService(store.workspace)
        self._generator = generator
        self._affection = affection

    async def ensure_seeded(self, role_id: str, snapshot: RoleModelSnapshot):
        """Prepares SELF, then affection, before prompt construction.

        Both use the role dialogue model; either failure stops the turn and the
        next message retries whatever is still missing.
        """
        if snapshot.role_id != role_id or snapshot.purpose != "chat":
            raise ValueError("SELF.md 初始化需要当前角色的对话模型")
        with self._store.lock:
            role = self._required_role(role_id)
            state = self._memory.prepare_memory(role)
            if state != role.memory_init_state:
                role = self._store.update_role(role_id, memory_init_state=state)
        seed = dict(state["self_seed"])
        if seed["status"] != "pending":
            # SELF was ready before this turn: memory and conversation also count.
            await self._ensure_affection(role, snapshot, established=True)
            return
        seed.update(
            model_registration_id=snapshot.registration_id,
            last_attempt_at=now_iso(),
            last_error=None,
        )
        self._save_seed(role_id, seed)
        try:
            content = await self._generator.agenerate(role, snapshot)
        except (Exception, asyncio.CancelledError) as error:
            seed["last_error"] = str(error) or type(error).__name__
            self._save_seed(role_id, seed)
            if isinstance(error, asyncio.CancelledError):
                raise
            raise SelfInitializationError(
                "SELF.md 初始化失败，请再次发送消息重试"
            ) from error

        path = self._memory.memory_root(role_id) / "SELF.md"
        # No await between the final edit check and commit. Never overwrite a changed document.
        with self._store.lock:
            current = self._required_role(role_id)
            current_seed = resolve_self_seed_state(
                current, path.read_text(encoding="utf-8")
            )
            if (
                current_seed["status"] != "pending"
                or current_seed["fingerprint"] != seed["fingerprint"]
            ):
                self._save_seed(role_id, {**current_seed, "status": "user_edited"})
            else:
                content = normalize_memory_document("SELF.md", content)
                temporary = path.with_suffix(".md.tmp")
                try:
                    _ = temporary.write_text(content, encoding="utf-8")
                    _ = temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
                seed.update(
                    status="generated",
                    generated_at=now_iso(),
                    fingerprint=self_fingerprint(content),
                )
                self._save_seed(role_id, seed)
            ready = self._required_role(role_id)
        # SELF is ready (generated now or edited meanwhile): seed from the profile.
        await self._ensure_affection(ready, snapshot, established=False)

    async def _ensure_affection(
        self, role: RoleRecord, snapshot: RoleModelSnapshot, *, established: bool
    ) -> None:
        try:
            await self._affection.ensure_initialized(
                role, snapshot, established=established
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise SelfInitializationError(
                "好感度初始化失败，请再次发送消息重试"
            ) from error

    def _required_role(self, role_id: str):
        role = self._store.get_role(role_id)
        if role is None:
            raise RoleNotFoundError(role_id)
        return role

    def _save_seed(self, role_id: str, seed: dict[str, Any]):
        with self._store.lock:
            role = self._required_role(role_id)
            current = role.memory_init_state.get("self_seed") or {}
            # An edit saved while the provider was running remains terminal after failure.
            if seed["status"] == "pending" and current.get("status") in {
                "generated",
                "user_edited",
            }:
                seed = {
                    **seed,
                    "status": current["status"],
                    "fingerprint": current["fingerprint"],
                }
            state = {**role.memory_init_state, "self_seed": seed}
            if state != role.memory_init_state:
                _ = self._store.update_role(role_id, memory_init_state=state)
