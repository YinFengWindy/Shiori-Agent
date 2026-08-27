"""关系快照优化与寂寞心跳后台循环。"""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..store import RoleStore
from .loneliness import _LONELINESS_TICK_MINUTES, _parse_iso
from .service import RoleRelationshipRuntimeService
from .snapshot import RelationshipSnapshotOptimizer

class RelationshipSnapshotLoop:
    """Runs the relationship snapshot optimizer on overdue roles."""

    def __init__(
        self,
        optimizer: RelationshipSnapshotOptimizer,
        *,
        role_store: RoleStore,
        runtime: RoleRelationshipRuntimeService,
        interval_seconds: int = 8 * 3600,
        recent_refresh_seconds: int = 4 * 3600,
        recent_window_seconds: int = 2 * 3600,
        now_fn=None,
    ) -> None:
        self._optimizer = optimizer
        self._role_store = role_store
        self._runtime = runtime
        self._interval = max(60, int(interval_seconds))
        self._recent_refresh = max(60, int(recent_refresh_seconds))
        self._recent_window = max(60, int(recent_window_seconds))
        self._now_fn = now_fn or datetime.now
        self._running = False

    async def run(self) -> None:
        self._running = True
        await self._catch_up_overdue_roles()
        while self._running:
            await asyncio.sleep(self._seconds_until_next_tick())
            if not self._running:
                break
            for role in self._role_store.list_roles():
                if not self._is_role_overdue(role.id, now=self._now_fn().astimezone()):
                    continue
                await self._optimizer.optimize(role_id=role.id)

    def stop(self) -> None:
        self._running = False

    async def _catch_up_overdue_roles(self) -> None:
        now = self._now_fn().astimezone()
        for role in self._role_store.list_roles():
            if self._is_role_overdue(role.id, now=now):
                await self._optimizer.optimize(role_id=role.id)

    def _is_role_overdue(self, role_id: str, *, now: datetime) -> bool:
        snapshot = self._runtime.read_snapshot(role_id)
        if snapshot is None:
            return True
        generated_at = _parse_iso(snapshot.get("generated_at"))
        if generated_at is None:
            return True
        last_activity = self._latest_activity(role_id)
        if last_activity is not None and (now - last_activity).total_seconds() <= self._recent_window:
            return (now - generated_at).total_seconds() >= self._recent_refresh
        return (now - generated_at).total_seconds() >= self._interval

    def _latest_activity(self, role_id: str) -> datetime | None:
        session_key = self._runtime._session_manager.role_session_key(role_id)
        last_user = self._runtime._presence.get_last_user_at(session_key) if self._runtime._presence else None
        last_proactive = self._runtime._presence.get_last_proactive_at(session_key) if self._runtime._presence else None
        if last_user is None:
            return last_proactive
        if last_proactive is None:
            return last_user
        return max(last_user, last_proactive)

    def _seconds_until_next_tick(self) -> float:
        now = self._now_fn()
        now_ts = now.replace(second=0, microsecond=0).timestamp()
        next_ts = (now_ts // self._interval + 1) * self._interval
        return max(1.0, next_ts - now.timestamp())


class LonelinessHeartbeatLoop:
    """Periodically refreshes per-role loneliness runtime values."""

    def __init__(
        self,
        runtime: RoleRelationshipRuntimeService,
        *,
        role_store: RoleStore,
        interval_seconds: int = _LONELINESS_TICK_MINUTES * 60,
    ) -> None:
        self._runtime = runtime
        self._role_store = role_store
        self._interval = max(30, int(interval_seconds))
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            now = datetime.now().astimezone()
            for role in self._role_store.list_roles():
                self._runtime.recompute_loneliness(role.id, now=now)

    def stop(self) -> None:
        self._running = False
