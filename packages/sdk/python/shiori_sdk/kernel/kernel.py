"""The plugin kernel: provide/require, ordered setup, scoped disposal and reload."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from . import graph
from .contracts import Key, KernelError, KernelState, PluginFailed, PluginSpec
from .contracts import PluginStarted, PluginStopped, Veto, plugin_logger
from .diagnostics import PluginDiagnostic
from .events import WATCH_LIMIT, Check, EventHub, OnHandler, WatchHandler
from .scope import Dispose, Scope

logger = logging.getLogger("shiori_sdk.kernel")

CORE = ""
"""Owner recorded for keys the host provides directly (core modules)."""

_DRAIN_TIMEOUT = "插件 {} 排空超时（{:g} 秒），重载已中止，保留旧实例"
DRAIN_TIMEOUT = 60.0
"""Seconds a reload waits for its closure to drain before giving up (D25)."""


@dataclass(frozen=True)
class PluginStatus:
    """Where one plugin stands: ACTIVE, FAILED, BLOCKED, REPLACED or STOPPED.

    ``error`` is the setup failure and ``cleanup_errors`` what releasing the
    plugin's scope reported (after a failed setup or a stop).
    """

    state: KernelState
    diagnostic: PluginDiagnostic | None = None
    error: BaseException | None = None
    cleanup_errors: tuple[Exception, ...] = ()


class Context:
    """Everything a plugin's ``setup`` receives from the kernel."""

    def __init__(self, kernel: Kernel, spec: PluginSpec, scope: Scope) -> None:
        self.plugin_id, self.data_dir, self.config = spec.id, spec.data_dir, spec.config
        self.log = plugin_logger(spec.id)
        self._kernel, self._spec, self._scope = kernel, spec, scope

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` under a key this plugin declares in ``provides``."""
        self._declared(key, self._spec.provides, "provides")
        self._kernel._register(key, impl, self.plugin_id, self._scope)

    def require[T](self, key: Key[T]) -> T:
        """The current provider of a key declared in ``inject``."""
        self._declared(key, self._spec.requires, "inject")
        if (found := self._kernel._providers.get(key.name)) is None:
            reason = f"插件 {self.plugin_id} 依赖的 {key.name} 当前没有提供方"
            code, ids = "provider_unavailable", [self.plugin_id]
            raise KernelError(code, "dependency", "inject", reason, ids)
        return found[1]

    def get[T](self, key: Key[T]) -> T | None:
        """The current provider of a key declared in ``optional_inject``, or None."""
        self._declared(key, self._spec.optional, "optional_inject")
        return self._kernel.get(key)

    def _declared(self, key: Key[Any], names: tuple[str, ...], field: str) -> None:
        if key.name not in names:
            reason = f"插件 {self.plugin_id} 未在 manifest {field} 中声明 {key.name}"
            code, ids = "undeclared_key", [self.plugin_id]
            raise KernelError(code, "setup", field, reason, ids)

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins the ordered chain; return the (replaced) event or ``Veto``."""
        self._kernel._events.on(self.plugin_id, self._scope, event_type, handler)

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to the final event, serially, without delaying emit."""
        self._kernel._events.watch(self.plugin_id, self._scope, event_type, handler)

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through the kernel; see ``Kernel.emit``."""
        return await self._kernel.emit(event)

    def effect(self, dispose: Dispose) -> None:
        """Registers cleanup, run LIFO after subscriptions and tasks are gone."""
        _ = self._scope.effect(dispose)

    def spawn[T](self, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """Runs a task owned by this plugin; disposal cancels it (not drained, D25)."""
        return self._scope.spawn(coro, name=f"plugin:{self.plugin_id}")

    def on_drain(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Adds plugin-specific draining to the default one before a reload (D25)."""
        self._scope.ensure_active("on_drain")
        self._scope.drainers.append(callback)


class Kernel:
    """Loads plugin specs in dependency order and owns their scopes.

    The host provides core keys with ``provide`` and adds post-chain checks
    with ``check`` before ``start``; ``reload`` and ``stop`` complete the host
    surface. ``activate`` / ``deactivate`` / ``drain`` are the steps those
    compose, for hosts that orchestrate enabling and rollback themselves.
    """

    def __init__(
        self, *, drain_timeout: float = DRAIN_TIMEOUT, watch_limit: int = WATCH_LIMIT
    ) -> None:
        self.drain_timeout = drain_timeout
        self._specs: dict[str, PluginSpec] = {}
        self._status: dict[str, PluginStatus] = {}
        self._scopes: dict[str, Scope] = {}
        self._providers: dict[str, tuple[str, Any]] = {}
        self._owners: dict[str, str] = {}
        self._rank: dict[str, int] = {}
        self._events = EventHub(lambda pid: self._rank.get(pid, -1), watch_limit)

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes a core service; a duplicate is an error (startup fails)."""
        self._register(key, impl, CORE, None)

    def get[T](self, key: Key[T]) -> T | None:
        """The current provider of ``key``; consumers look it up on every use."""
        return None if (found := self._providers.get(key.name)) is None else found[1]

    def check[E](self, event_type: type[E], check: Check[E]) -> None:
        """Adds a fixed core check run on the final event of each ``on`` chain."""
        self._events.check(event_type, check)

    async def emit[E](self, event: E) -> E | Veto:
        """``on`` chain by rank, then core checks, then watchers (not awaited)."""
        return await self._events.emit(event)

    def status(self, plugin_id: str) -> PluginStatus | None:
        """The plugin's latest status, None when the kernel never saw it."""
        return self._status.get(plugin_id)

    def order(self) -> tuple[str, ...]:
        """Every planned plugin in setup order: dependency depth, then id (§8.1)."""
        return tuple(self._rank)

    def _register(
        self, key: Key[Any], impl: object, owner: str, scope: Scope | None
    ) -> None:
        if scope is not None:
            scope.ensure_active(f"provide:{key.name}")
        if key.name in self._providers:
            holder = self._providers[key.name][0]
            names = [holder or "核心", owner or "核心"]
            reason = f"{key.name} 已由 {names[0]} 提供，{names[1]} 不能重复提供"
            raise KernelError("duplicate_provider", "setup", "provides", reason, names)
        self._providers[key.name] = (owner, impl)

    async def start(self, specs: Iterable[PluginSpec]) -> None:
        """Plans ``specs`` and sets up every runnable plugin that is not running.

        Register-only specs are ordered but not activated, so a later ``start``
        cannot run an untrusted or disabled plugin by accident. A plugin whose
        required key is unavailable becomes BLOCKED, one whose setup raises
        FAILED, and its ``require`` dependents BLOCKED in turn.
        """
        for plugin_id in await self.plan(specs):
            if self._specs[plugin_id].runnable and plugin_id not in self._scopes:
                _ = await self.activate(plugin_id)

    async def plan(self, specs: Iterable[PluginSpec]) -> tuple[str, ...]:
        """Adds ``specs``, re-plans all known specs and returns the setup order.

        Excluded plugins (see ``graph.plan``) get their status here and never
        run. Raises ``KernelError`` when a runnable plugin declares a core key.
        """
        self._specs.update((spec.id, spec) for spec in specs)
        core = {name for name, (owner, _) in self._providers.items() if owner == CORE}
        plan = graph.plan(list(self._specs.values()), core)
        self._rank = {plugin_id: rank for rank, plugin_id in enumerate(plan.order)}
        self._owners = plan.owners
        for plugin_id, excluded in plan.excluded.items():
            known = getattr(self._status.get(plugin_id), "diagnostic", None)
            if plugin_id not in self._scopes and known != excluded:
                _ = await self._settle(plugin_id, KernelState(excluded.state), excluded)
        return plan.order

    def scope(self, plugin_id: str) -> Scope:
        """The scope of a running (or setting up) plugin, for host adapters."""
        return self._scopes[plugin_id]

    async def activate(self, plugin_id: str) -> PluginStatus:
        """Runs one planned plugin's setup; on failure releases what it registered.

        A register-only spec is refused and left unchanged. Cancellation also
        releases the scope, then propagates.
        """
        spec = self._specs[plugin_id]
        if not spec.runnable:
            reason = f"插件 {plugin_id} 只登记，不能启动"
            raise KernelError("not_runnable", "setup", "runnable", reason, [plugin_id])
        if missing := [name for name in spec.requires if name not in self._providers]:
            # ``field`` names the first missing ``requires`` entry by index; a
            # key no spec declares is missing, a declared one is unavailable.
            name, field = missing[0], f"inject[{spec.requires.index(missing[0])}]"
            known = name in self._owners
            code = "dependency_unavailable" if known else "missing_dependency"
            reason = f"插件 {plugin_id} 依赖的 {name} {'未启用或加载失败' if known else '不存在'}"
            blocked = PluginDiagnostic(code, "dependency", field, reason)
            return await self._settle(plugin_id, KernelState.BLOCKED, blocked)
        scope = self._scopes[plugin_id] = Scope(plugin_id)
        try:
            await spec.setup(Context(self, spec, scope))
        except BaseException as error:
            errors = tuple(await self._release(plugin_id))
            reason = f"插件 {plugin_id} 启动失败: {str(error) or type(error).__name__}"
            state = KernelState.FAILED
            failed = PluginDiagnostic(
                "setup_failed", "setup", "setup", reason, "", state
            )
            if not isinstance(error, Exception):
                self._status[plugin_id] = PluginStatus(state, failed, error, errors)
                raise
            return await self._settle(plugin_id, state, failed, error, errors)
        return await self._settle(plugin_id, KernelState.ACTIVE)

    async def deactivate(self, plugin_id: str) -> list[Exception]:
        """Releases a plugin's scope (stopped or failed) and marks it STOPPED."""
        if plugin_id not in self._scopes:
            return []
        errors = await self._release(plugin_id)
        _ = await self._settle(plugin_id, KernelState.STOPPED, cleanup=tuple(errors))
        return errors

    async def _release(self, plugin_id: str) -> list[Exception]:
        for name, (owner, _) in list(self._providers.items()):
            if owner == plugin_id:
                del self._providers[name]
        errors = await self._scopes[plugin_id].close()
        del self._scopes[plugin_id]
        return errors

    async def _settle(
        self,
        plugin_id: str,
        state: KernelState,
        problem: PluginDiagnostic | None = None,
        error: BaseException | None = None,
        cleanup: tuple[Exception, ...] = (),
    ) -> PluginStatus:
        status = self._status[plugin_id] = PluginStatus(state, problem, error, cleanup)
        if state is KernelState.ACTIVE:
            _ = await self.emit(PluginStarted(plugin_id))
        elif state is KernelState.STOPPED:
            _ = await self.emit(PluginStopped(plugin_id))
        elif problem is not None and state in (KernelState.FAILED, KernelState.BLOCKED):
            _ = await self.emit(PluginFailed(plugin_id, problem))
        return status

    def closure(
        self, plugin_id: str, *, optional: bool, among: Iterable[str] | None = None
    ) -> list[str]:
        """``plugin_id`` and its dependents in ``among``, dependents first.

        ``among`` defaults to the running plugins; ``optional`` also takes
        ``optional_inject`` consumers (a reload set, §8.2), otherwise only
        ``requires`` dependents (what disabling a provider takes down).
        """
        pool = {plugin_id, *(self._scopes if among is None else among)}
        members = {pid: self._specs[pid] for pid in pool}
        found = graph.dependents(plugin_id, members, self._owners, optional)
        return sorted(found, key=lambda pid: self._rank.get(pid, -1), reverse=True)

    def restart_only(self, plugin_ids: Iterable[str]) -> KernelError | None:
        """The refusal for plugins only a restart may change (D14), or None.

        ``diagnostic.field`` says why: ``channels`` (checked first) or
        ``supports_hot_unload``; ``plugin_ids`` names the plugins.
        """
        specs = [self._specs[pid] for pid in plugin_ids]
        for field, ids in (
            ("channels", sorted(s.id for s in specs if s.channels)),
            ("supports_hot_unload", sorted(s.id for s in specs if not s.hot_reload)),
        ):
            if ids:
                reason = f"插件 {'、'.join(ids)} 不可代内重载，需重启"
                return KernelError("restart_required", "reload", field, reason, ids)
        return None

    def reload_closure(self, plugin_id: str) -> list[str]:
        """The reload set of ``plugin_id``, dependents first, or ``KernelError``.

        Refused when the plugin is not running or the set holds a plugin only
        a restart can change (D14: channels or ``hot_reload=False``).
        """
        if getattr(self._status.get(plugin_id), "state", None) != KernelState.ACTIVE:
            reason = f"插件 {plugin_id} 未在运行，无法重载"
            raise KernelError("not_active", "reload", "state", reason, [plugin_id])
        members = self.closure(plugin_id, optional=True)
        if refusal := self.restart_only(members):
            raise refusal
        return members

    async def reload(
        self, plugin_id: str, *, timeout: float | None = None
    ) -> tuple[str, ...]:
        """Drains, disposes and sets up again the ``reload_closure``.

        Abandoned with the old instances kept when draining exceeds
        ``timeout`` (default ``drain_timeout``). Returns the reloaded ids in
        setup order; ``status`` tells each outcome.
        """
        members = self.reload_closure(plugin_id)
        await self.drain(members, timeout)
        for pid in members:
            _ = await self.deactivate(pid)
        for pid in reversed(members):
            _ = await self.activate(pid)
        return tuple(reversed(members))

    async def drain(
        self,
        plugin_ids: Sequence[str],
        timeout: float | None = None,
        prepare: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Drains the plugins one after another within one total timeout.

        ``prepare`` (host hook) runs before each plugin's drain. A timeout
        raises ``KernelError`` naming the plugin being drained; then, as on an
        ``on_drain`` error or cancellation, the remaining plugins are skipped
        while the drain in progress finishes in the background (it only waits).
        """
        limit = self.drain_timeout if timeout is None else timeout
        abandoned, current = False, ""

        async def staged() -> None:
            nonlocal current
            for current in plugin_ids:
                if prepare is not None and not abandoned:
                    await prepare(current)
                if abandoned:
                    return
                await self._scopes[current].drain()

        waiting = asyncio.ensure_future(staged())
        try:
            if not (await asyncio.wait({waiting}, timeout=limit))[0]:
                reason = _DRAIN_TIMEOUT.format(current, limit)
                code, field = "drain_timeout", "on_drain"
                raise KernelError(code, "reload", field, reason, [current])
            waiting.result()
        except BaseException:
            abandoned = True
            if not waiting.done():
                waiting.add_done_callback(_log_abandoned)
            raise

    async def stop(self) -> list[Exception]:
        """Releases every plugin scope, dependents first; returns the cleanup errors."""
        errors: list[Exception] = []
        for pid in sorted(self._scopes, key=lambda pid: -self._rank.get(pid, -1)):
            errors.extend(await self.deactivate(pid))
        return errors


def _log_abandoned(task: asyncio.Future[None]) -> None:
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("已放弃的插件排空以异常结束", exc_info=error)
