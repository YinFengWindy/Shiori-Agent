"""寂寞心跳后台循环。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from .loneliness import _LONELINESS_TICK_MINUTES
from .service import RoleRelationshipRuntimeService

logger = logging.getLogger(__name__)


class LonelinessHeartbeatLoop:
    """Periodically refreshes per-role loneliness and settles affection decay."""

    def __init__(
        self,
        runtime: RoleRelationshipRuntimeService,
        *,
        interval_seconds: int = _LONELINESS_TICK_MINUTES * 60,
    ) -> None:
        self._runtime = runtime
        self._interval = max(30, int(interval_seconds))
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            now = datetime.now().astimezone()
            for role in self._runtime.sources.list_roles():
                try:
                    # Decay can never cross the loneliness threshold (the floor
                    # keeps 亲密), so the two settle independently.
                    self._runtime.affection.settle_decay(role.id, now=now)
                    self._runtime.recompute_loneliness(role.id, now=now)
                    await self._runtime.notify_status_changed(role.id)
                except Exception:
                    # This loop is the boundary: nobody awaits it, so an error
                    # raised here would silently stop the heartbeat for every
                    # role. Log it and move on; the broken role's next read
                    # still raises. Cancellation is not an Exception.
                    logger.exception("Relationship heartbeat failed: role=%s", role.id)

    def stop(self) -> None:
        self._running = False
