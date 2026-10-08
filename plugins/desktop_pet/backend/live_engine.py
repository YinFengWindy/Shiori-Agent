"""The pet's live-chat engine: lifecycle of the single live run.

At most one run exists (single room, single role). ``LiveStartGate`` decides
whether a role may start; the run ends by itself when the role stops being
the pet's role, Bilibili refuses it, or the plugin shuts down. Once shut down
the engine never starts a run again, even one whose start was still waiting
on Bilibili.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.roles import Roles

from .bilibili_live_api import BilibiliLiveApi
from .live_config import LiveConfig, LiveConfigStore
from .live_gate import LiveStartGate
from .live_output import LiveReplyOutcome
from .live_session import LiveSession, LiveSessionDeps
from .live_status import status_shape


class LiveEngine:
    """Owns the current run and the last ended run's status per role."""

    def __init__(
        self,
        *,
        roles: Roles,
        gate: LiveStartGate,
        configs: LiveConfigStore,
        api: BilibiliLiveApi,
        deps: LiveSessionDeps,
    ) -> None:
        self.gate = gate
        self._roles = roles
        self._configs = configs
        self._api = api
        self._deps = deps
        self._session: LiveSession | None = None
        self._ended: dict[str, dict[str, Any]] = {}
        self._start_lock = asyncio.Lock()
        self._closed = False

    async def start(self, role_id: str) -> dict[str, Any]:
        """Start a run for the pet's role; every precondition failure raises."""
        async with self._start_lock:
            self._require_open()
            if self._session is not None:
                raise ValueError("已有直播互动在运行，请先结束")
            config = await self.gate.check(role_id)
            assert config.room_id is not None
            room = await self._api.fetch_room(config.room_id)
            buvid = await self._api.fetch_buvid()
            # Shutdown or a binding change may have happened while Bilibili answered.
            self._require_open()
            self.gate.require_pet_role(role_id)
            session = LiveSession(
                role_id=role_id,
                room=room,
                buvid=buvid,
                config=config,
                deps=self._deps,
                on_ended=self._ended_session,
            )
            self._ended.pop(role_id, None)
            self._session = session
            session.start()
            return self.status(role_id)

    async def pause(self, role_id: str) -> dict[str, Any]:
        """Pause the role's run."""
        await self._require_session(role_id).pause()
        return self.status(role_id)

    async def resume(self, role_id: str) -> dict[str, Any]:
        """Resume the role's paused run."""
        self._require_session(role_id).resume()
        return self.status(role_id)

    async def stop(self, role_id: str) -> dict[str, Any]:
        """End the role's run."""
        await self._require_session(role_id).stop("已手动结束")
        return self.status(role_id)

    def status(self, role_id: str) -> dict[str, Any]:
        """The role's run, its last ended run, or idle — always the same shape.

        ``configured_room_id`` is the saved room; ``room`` is the room the run
        actually uses, which differs after the room was changed mid-run.
        """
        self.gate.require_role(role_id)
        session = self._session
        if session is not None and session.role_id == role_id:
            current = session.snapshot()
        else:
            current = self._ended.get(role_id) or status_shape(role_id)
        return {**current, "configured_room_id": self._configs.read(role_id).room_id}

    def apply_config(self, role_id: str, config: LiveConfig) -> None:
        """A saved config reaches the role's run at once (timing only)."""
        session = self._session
        if session is not None and session.role_id == role_id:
            session.apply_config(config)

    async def outcome(self, outcome: LiveReplyOutcome) -> None:
        """``LiveReplyOutput`` listener: route a pet outcome to the current run."""
        if self._session is not None:
            self._session.outcome(outcome)

    async def on_role_deleted(self, event: RoleDeleted) -> None:
        """A deleted role's run ends and its settings are removed."""
        session = self._session
        if session is not None and session.role_id == event.role_id:
            await session.stop("角色已删除")
        self._ended.pop(event.role_id, None)
        self._configs.delete(event.role_id)

    def prune_deleted_roles(self) -> None:
        """Remove settings of roles deleted while the plugin was disabled."""
        self._configs.prune({role.id for role in self._roles.list_roles()})

    async def shutdown(self) -> None:
        """Plugin disable: refuse new runs, end the current one, cancel its output."""
        self._closed = True
        if self._session is not None:
            await self._session.stop("桌宠插件已停用")

    def _ended_session(self, session: LiveSession) -> None:
        if self._session is session:
            self._session = None
        self._ended[session.role_id] = session.snapshot()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("桌宠插件已停用，无法开始直播互动")

    def _require_session(self, role_id: str) -> LiveSession:
        session = self._session
        if session is None or session.role_id != role_id:
            raise ValueError("该角色没有进行中的直播互动")
        return session
