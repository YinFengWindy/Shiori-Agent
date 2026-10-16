"""Per-instance admission and in-flight accounting for host-routed plugin calls."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.tool_hooks import HookOutcome
from shiori_sdk.tools import Tool

# Gates that registered one tool object, kept on the object itself. A tool kept
# in a process resource can be registered by several instances or generations.
_TOOL_GATES = "__plugin_call_gates__"
# Same bookkeeping for the ``run`` of a contributed phase module or tool hook.
_RUN_GATES = "__plugin_run_gates__"


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
        self._retired = False
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
    def retired(self) -> bool:
        """Whether the instance was disposed; a retired gate never reopens."""
        return self._retired

    @property
    def in_flight(self) -> int:
        """Number of admitted calls that have not finished yet."""
        return self._in_flight

    def seal(self) -> None:
        """Rejects new calls; already admitted calls keep running."""
        self._open = False

    def reopen(self) -> None:
        """Admits calls again after an abandoned transition, unless retired."""
        self._open = not self._retired

    def retire(self) -> None:
        """Seals for good: the instance is being disposed and never admits again."""
        self._retired = True
        self._open = False

    async def wait_idle(self) -> None:
        """Waits until every admitted call has finished."""
        _ = await self._idle.wait()

    def guard[**P, R](
        self, call: Callable[P, Awaitable[R]]
    ) -> Callable[P, Awaitable[R]]:
        """Wraps one plugin callable with this instance's admission and accounting.

        RPC handlers and service methods are wrapped per registration and are
        not shared across instances, so one gate suffices; only tool objects
        (see ``guard_tool``) can outlive an instance and need a gate list.
        """
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
        self._guard_method(tool, "execute", _TOOL_GATES, skipped=None)

    def guard_phase_module(self, module: object) -> None:
        """Gates a contributed phase module's ``run`` like a tool call.

        A run admitted while the instance is open is waited for by a reload.
        Once no registering instance admits (reload drain, disposal), the
        module passes its frame through unchanged instead of failing the
        turn: a phase built before the reload keeps referencing it, and the
        plugin is simply absent for that run.
        """
        self._guard_method(module, "run", _RUN_GATES, skipped=_pass_frame)

    def guard_tool_hook(self, hook: object) -> None:
        """Gates a contributed tool hook's ``run``; a sealed hook passes the call."""
        self._guard_method(hook, "run", _RUN_GATES, skipped=_pass_hook)

    def _guard_method(
        self,
        target: object,
        method: str,
        gates_attribute: str,
        *,
        skipped: Callable[..., Any] | None,
    ) -> None:
        """Wraps ``target.<method>`` in place, shared by every gate that registers it.

        ``skipped`` produces the result when no gate admits the call; ``None``
        rejects it with ``plugin_unavailable`` instead.
        """
        gates: list[PluginCallGate] | None = vars(target).get(gates_attribute)
        if gates is None:
            gates = []
            call = getattr(target, method)
            target_gates = gates

            @functools.wraps(call)
            async def admitted(*args: Any, **kwargs: Any) -> Any:
                _prune(target_gates)
                if skipped is not None and not any(gate.open for gate in target_gates):
                    return skipped(*args, **kwargs)
                return await PluginCallGate._call_through(
                    tuple(target_gates), call, *args, **kwargs
                )

            setattr(target, gates_attribute, gates)
            setattr(target, method, admitted)
        _prune(gates)
        # One instance may contribute the same object more than once (e.g. to
        # two phase slots); it still admits each call once.
        if self not in gates:
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


def _prune(gates: list[PluginCallGate]) -> None:
    """Drops gates of disposed instances once their admitted calls finished."""
    gates[:] = [gate for gate in gates if not gate.retired or gate.in_flight]


def _pass_frame(frame: Any) -> Any:
    """Result of a skipped phase module run: the frame, unchanged."""
    return frame


def _pass_hook(*_args: Any) -> HookOutcome:
    """Result of a skipped tool hook run: let the call proceed unchanged."""
    return HookOutcome()
