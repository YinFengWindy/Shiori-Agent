from __future__ import annotations

import asyncio
from collections.abc import Coroutine


class _LoopBridgeMixin:
    """Makes the NcatBot loop boundary explicit for inbound and outbound work."""

    def _require_main_loop(self) -> asyncio.AbstractEventLoop:
        if self._main_loop is None:
            raise RuntimeError("QQ main loop 未就绪")
        return self._main_loop

    def _submit_to_main_loop(self, coro: Coroutine[object, object, None]) -> None:
        asyncio.run_coroutine_threadsafe(coro, self._require_main_loop())

    async def _run_on_bot_loop(self, coro: Coroutine[object, object, object]) -> object:
        if self._bot_loop is None:
            raise RuntimeError("QQ bot loop 未就绪")
        future = asyncio.run_coroutine_threadsafe(coro, self._bot_loop)
        return await asyncio.wrap_future(future)
