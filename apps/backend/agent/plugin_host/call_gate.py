"""Per-instance admission and in-flight accounting for host-routed plugin calls."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.tools import Tool

# Gates that registered one tool object, kept on the object itself. A tool kept
# in a process resource can be registered by several instances or generations.
_TOOL_GATES = "__plugin_call_gates__"


class PluginCallGate:
    """Admits tool, service and RPC calls into one plugin instance until sealed.

    Every callable a plugin registers through its tools, services or RPC
    capability is wrapped here, so the kernel can stop new calls reaching an
    instance that is about to be replaced and wait for the accepted ones to
    finish. A sealed gate rejects instead of queueing: a caller holding a
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
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def open(self) -> bool:
        """Whether new calls are admitted."""
        return self._open

    @property
    def in_flight(self) -> int:
        """Number of admitted calls that have not finished yet."""
        return self._in_flight

    def seal(self) -> None:
        """Rejects new calls; already admitted calls keep running."""
        self._open = False

    def reopen(self) -> None:
        """Admits calls again after an abandoned transition."""
        self._open = True

    async def wait_idle(self) -> None:
        """Waits until every admitted call has finished."""
        _ = await self._idle.wait()

    def guard[**P, R](
        self, call: Callable[P, Awaitable[R]]
    ) -> Callable[P, Awaitable[R]]:
        """Wraps one plugin callable with this instance's admission and accounting."""
        gates = (self,)

        @functools.wraps(call)
        async def admitted(*args: P.args, **kwargs: P.kwargs) -> R:
            return await PluginCallGate._call_through(gates, call, *args, **kwargs)

        return admitted

    def guard_tool(self, tool: Tool) -> None:
        """Gates ``tool.execute`` on the object, for every instance that registers it.

        The tool keeps its identity because callers also reach it outside the
        registry (snapshotted tool maps, exported plugin APIs). The object
        carries the list of gates that registered it: a call is admitted while
        any of them is open and counted by every open one, so each instance
        waits for exactly the calls it admitted.
        """
        gates: list[PluginCallGate] | None = tool.__dict__.get(_TOOL_GATES)
        if gates is None:
            gates = []
            execute = tool.execute

            async def admitted(**kwargs: Any) -> Any:
                return await PluginCallGate._call_through(
                    tuple(gates), execute, **kwargs
                )

            setattr(tool, _TOOL_GATES, gates)
            setattr(tool, "execute", admitted)
        # Retired instances stop mattering once they are sealed and idle.
        gates[:] = [gate for gate in gates if gate.open or gate.in_flight]
        gates.append(self)

    def _enter(self) -> None:
        self._in_flight += 1
        self._idle.clear()

    def _exit(self) -> None:
        self._in_flight -= 1
        if not self._in_flight:
            self._idle.set()

    @staticmethod
    async def _call_through[R](
        gates: Sequence[PluginCallGate],
        call: Callable[..., Awaitable[R]],
        *args: Any,
        **kwargs: Any,
    ) -> R:
        admitting = [gate for gate in gates if gate.open]
        if not admitting:
            plugin_id = gates[-1].plugin_id if gates else "?"
            raise PluginRpcError(
                "plugin_unavailable",
                f"插件 {plugin_id} 正在重载或已停用，本次调用未执行",
            )
        for gate in admitting:
            gate._enter()
        try:
            return await call(*args, **kwargs)
        finally:
            for gate in admitting:
                gate._exit()
