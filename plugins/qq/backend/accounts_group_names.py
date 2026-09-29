"""Per-account cache of QQ group names for inbound message snapshots."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from websockets.exceptions import ConnectionClosed

from .onebot import OneBotError

logger = logging.getLogger(__name__)
# How long a fetched group name is reused before NapCat is asked again.
GROUP_NAME_TTL_SECONDS = 600.0


class QQGroupNames:
    """Caches each account's group names in memory, refetching after the TTL.

    ``fetch(account_id, group_id)`` returns the platform's current group name.
    Each account keeps its own entries, since accounts see different groups.
    """

    def __init__(
        self,
        fetch: Callable[[str, str], Awaitable[str]],
        *,
        ttl_seconds: float = GROUP_NAME_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._clock = clock
        self._names: dict[str, dict[str, tuple[str, float]]] = {}

    async def name(self, account_id: str, group_id: str) -> str | None:
        """The group's name, or None when it is blank or NapCat cannot tell.

        A failed query only costs the message its group name: it is logged
        and the message proceeds without one. Failures are NapCat errors
        (including an offline account and an in-flight reply lost to a
        disconnect), a reply timeout, or the socket closing while sending.
        """
        groups = self._names.setdefault(account_id, {})
        cached = groups.get(group_id)
        now = self._clock()
        if cached is not None and now - cached[1] < self._ttl:
            return cached[0] or None
        try:
            name = await self._fetch(account_id, group_id)
        except (OneBotError, TimeoutError, ConnectionClosed) as exc:
            logger.warning(
                "[qq] 账号 %s 群 %s 名称查询失败，消息不带群名: %s",
                account_id,
                group_id,
                exc,
            )
            return None
        groups[group_id] = (name, now)
        return name or None
