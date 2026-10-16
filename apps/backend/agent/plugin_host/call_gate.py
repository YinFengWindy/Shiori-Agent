"""Per-instance admission and in-flight accounting for host-routed plugin calls."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.tools import Tool

# Marks a wrapper produced by a gate so a tool object registered again (e.g.
# kept in a process resource across reloads) is re-gated, not double-gated.
_GATED_MARKER = "__plugin_call_gate__"


class PluginCallGate:
    """Admits tool, service and RPC calls into one plugin instance until closed.

    Every callable a plugin registers through its tools, services or RPC
    capability is wrapped here, so the kernel can stop new calls reaching an
    instance that is about to be unloaded and wait for the accepted ones to
    finish. A closed gate rejects instead of queueing: a caller holding a
    stale reference must never be handed to a different instance, and a
    queued call from inside the reload closure would deadlock the drain.
    """

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id
        self._open = True
        self._in_flight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def in_flight(self) -> int:
        """Number of admitted calls that have not finished yet."""
        return self._in_flight

    def guard[**P, R](
        self, call: Callable[P, Awaitable[R]]
    ) -> Callable[P, Awaitable[R]]:
        """Wraps one plugin callable with this instance's admission and accounting."""
        original = getattr(call, "__wrapped__", call) if _is_gated(call) else call

        @functools.wraps(original)
        async def admitted(*args: P.args, **kwargs: P.kwargs) -> R:
            if not self._open:
                raise PluginRpcError(
                    "plugin_unavailable",
                    f"插件 {self._plugin_id} 正在重载或已停用，本次调用未执行",
                )
            self._in_flight += 1
            self._idle.clear()
            try:
                return await original(*args, **kwargs)
            finally:
                self._in_flight -= 1
                if not self._in_flight:
                    self._idle.set()

        setattr(admitted, _GATED_MARKER, True)
        return admitted

    def guard_tool(self, tool: Tool) -> None:
        """Gates ``tool.execute`` on the instance itself.

        The tool object keeps its identity because callers also reach it
        outside the registry (snapshotted tool maps, exported plugin APIs);
        gating the object covers every path.
        """
        setattr(tool, "execute", self.guard(tool.execute))

    async def close(self) -> None:
        """Rejects new calls, then waits until every admitted call has finished."""
        self._open = False
        _ = await self._idle.wait()


def _is_gated(call: Callable[..., Any]) -> bool:
    return bool(getattr(call, _GATED_MARKER, False))
