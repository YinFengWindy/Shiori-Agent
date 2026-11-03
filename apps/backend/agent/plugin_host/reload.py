"""In-generation reload and toggling of a plugin closure, with config rollback.

``shiori_sdk.kernel`` decides which plugins form a reload closure (target,
dependents and optional consumers) and owns draining, disposal and setup;
this module composes those steps with the host's config tables: drain the
closure (abandoning unchanged on timeout or cancellation), then replace it
under a process-resource hold, rolling back to the old config if the new
one fails.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.state import PluginView
from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.unload import (
    PluginReloadFailed,
    PluginReloadTimeout,
)

logger = logging.getLogger(__name__)


class ProcessResourceHold(Protocol):
    """Resources one in-generation reload keeps alive until ``release``."""

    async def release(self) -> list[BaseException]:
        """Ends the hold and returns close failures of resources nobody re-acquired."""
        ...


class ProcessResourceSource(Protocol):
    """The process-level owner a generation retains resources through.

    The concrete owner lives with the PROCESSES provider
    (``infra.process.resources.ProcessResourceOwner``). This protocol is the
    seam the assembly layer can call without importing that module.
    """

    def retain(self, generation: str, plugins: Iterable[str]) -> ProcessResourceHold:
        """Keeps ``plugins``' resources while their instances reload."""
        ...


@dataclass(frozen=True)
class PluginReloadResult:
    """Outcome of a successful in-generation reload."""

    # Every plugin set up again, target first, in dependency order.
    plugin_ids: tuple[str, ...]
    # Disposal and process-resource close failures; the new instances are ACTIVE.
    cleanup_errors: tuple[BaseException, ...]


@dataclass(frozen=True)
class ReloadSteps:
    """Operations a reload composes without owning or mirroring lifecycle state."""

    # Drains the closure (dependents first) within the timeout through the
    # kernel; abandons with every instance unchanged on timeout, ``on_drain``
    # failure or cancellation (``PluginReloadTimeout`` on timeout).
    drain: Callable[[list[PluginRecord], float], Awaitable[None]]
    # Disposes one handle and drops it from the kernel; returns cleanup errors.
    dispose: Callable[[PluginRecord], Awaitable[list[Exception]]]
    # Activate a record and derive its resulting presentation snapshot.
    activate: Callable[[PluginRecord, frozenset[str]], Awaitable[PluginView]]
    # Holds the plugins' process resources across the swap, when the host has any.
    retain: Callable[[tuple[str, ...]], ProcessResourceHold | None]
    # A live gate is optional for a failed or disabled presentation snapshot.
    calls: Callable[[PluginRecord], PluginCallGate | None]


@dataclass(frozen=True)
class ConfigTables:
    """The live generation config tables (expanded and raw) shared with the host."""

    values: dict[str, dict[str, Any]]
    raw: dict[str, dict[str, Any]]

    def swap(
        self,
        plugin_id: str,
        values: dict[str, Any] | None,
        raw: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Replaces one plugin's tables; returns the replaced ones (None = absent)."""
        previous = (self.values.get(plugin_id), self.raw.get(plugin_id))
        for tables, table in ((self.values, values), (self.raw, raw)):
            if table is None:
                _ = tables.pop(plugin_id, None)
            else:
                tables[plugin_id] = table
        return previous


def hot_unload_blockers(records: Iterable[PluginRecord]) -> list[str]:
    """Plugin ids among ``handles`` that declare ``supports_hot_unload: false``."""
    return [
        record.manifest.id
        for record in records
        if not record.manifest.supports_hot_unload
    ]


def _target_last(closure: list[PluginView], target: str) -> list[PluginView]:
    """``closure`` with ``target`` moved last, the others in their order.

    The kernel ranks a closure dependents first, but plugins that inject each
    other optionally may rank the target before a consumer; the target is
    still disposed last and set up first, so its consumers see the new one.
    """
    return [
        *(handle for handle in closure if handle.plugin_id != target),
        *(handle for handle in closure if handle.plugin_id == target),
    ]


async def reload_closure(
    target: str,
    closure: list[PluginView],
    *,
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None = None,
    on_replaced: Callable[[tuple[str, ...]], None] | None = None,
) -> PluginReloadResult:
    """Drains ``closure`` (dependents first, ``target`` last), then replaces it.

    Until the drain completes nothing is disposed: a timeout, an ``on_drain``
    failure or caller cancellation reopens every gate and leaves the old
    instances and tables in place. Once draining succeeded the replacement
    runs to completion even if the caller is cancelled meanwhile, including
    ``commit`` (see ``PluginKernel.reload``).
    """
    closure = _target_last(closure, target)
    await steps.drain([view.record for view in closure], drain_timeout)
    plugin_ids = frozenset(handle.plugin_id for handle in closure)
    replacement = asyncio.create_task(
        _replace(
            target,
            closure,
            values=values,
            raw_values=raw_values,
            tables=tables,
            steps=steps,
            drain_timeout=drain_timeout,
            commit=commit,
            on_replaced=on_replaced,
            reactivating=plugin_ids,
            restoring=plugin_ids,
            strict=True,
        )
    )
    return await _run_to_completion(replacement)


async def toggle_closure(
    target: str,
    closure: list[PluginView],
    *,
    enabled: bool,
    staying: frozenset[str],
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None = None,
    on_replaced: Callable[[tuple[str, ...]], None] | None = None,
) -> PluginReloadResult:
    """Loads (``enabled``) or unloads ``closure``, dependents first, ``target`` last.

    ``staying`` names the ACTIVE plugins in ``closure`` the toggle does not
    turn on or off (optional consumers of the target, with their dependents).
    They are only set up again around the target, so they are drained first
    as on a reload (abandoning unchanged on timeout or cancellation) and their
    setup sees ``was_active``. Nothing else is drained: disabling cancels
    in-flight work, as a generation swap does. The closure is disposed and
    loaded again under the new tables, which leaves disabled plugins DISABLED
    or BLOCKED and enabled ones ACTIVE, or FAILED when their setup fails (kept,
    as a generation swap would). Only a failing ``commit`` restores the
    previous tables and states. Once draining succeeded it runs to completion
    even if the caller is cancelled (see ``PluginKernel.set_enabled``).
    """
    closure = _target_last(closure, target)
    if staying:
        await steps.drain(
            [handle.record for handle in closure if handle.plugin_id in staying],
            drain_timeout,
        )
    replacement = asyncio.create_task(
        _replace(
            target,
            closure,
            values=values,
            raw_values=raw_values,
            tables=tables,
            steps=steps,
            drain_timeout=drain_timeout,
            commit=commit,
            on_replaced=on_replaced,
            # Neither a newly enabled plugin nor one turned off was active
            # right before this setup; a staying or restored one was.
            reactivating=staying,
            restoring=(
                staying
                if enabled
                else frozenset(handle.plugin_id for handle in closure)
            ),
            strict=False,
        )
    )
    return await _run_to_completion(replacement)


async def _run_to_completion(
    task: asyncio.Task[PluginReloadResult],
) -> PluginReloadResult:
    """Awaits ``task`` without letting caller cancellation interrupt it."""
    cancelled = False
    while not task.done():
        try:
            _ = await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        # The outcome is consistent either way; the caller asked to stop and
        # will not see it, so it is logged here.
        if task.cancelled():
            logger.error("调用方取消后，插件重载任务被取消")
        elif isinstance(error := task.exception(), PluginReloadFailed):
            logger.error(
                "调用方取消后插件重载失败，已恢复原配置；未恢复: %s",
                list(error.restore_failed),
                exc_info=error,
            )
        elif error is not None:
            logger.error("调用方取消后插件重载异常结束", exc_info=error)
        else:
            logger.warning(
                "调用方取消后插件重载仍已完成，新配置已生效: %s",
                list(task.result().plugin_ids),
            )
        raise asyncio.CancelledError
    return task.result()


async def _replace(
    target: str,
    closure: list[PluginView],
    *,
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None,
    on_replaced: Callable[[tuple[str, ...]], None] | None,
    reactivating: frozenset[str],
    restoring: frozenset[str],
    strict: bool,
) -> PluginReloadResult:
    """Disposes ``closure`` (``target`` last) and loads it again under the new tables.

    ``reactivating`` / ``restoring`` name the plugins whose setup sees
    ``was_active`` when loading the new / restoring the old tables. With
    ``strict`` a plugin that does not become ACTIVE fails the transition like
    a failing ``commit``; a failed transition restores every closure plugin to
    its previous state.
    """
    records = [handle.record for handle in reversed(closure)]
    plugin_ids = tuple(record.manifest.id for record in records)
    before = {handle.plugin_id: handle.state for handle in closure}
    retention = steps.retain(plugin_ids)
    errors: list[BaseException] = []
    failed: dict[str, BaseException] = {}
    restore_failed: dict[str, BaseException] = {}
    try:
        for handle in closure:
            errors.extend(await steps.dispose(handle.record))
        previous = tables.swap(target, values, raw_values)
        handles = await _activate(records, steps, reactivating)
        if strict:
            failed = _diverged(records, handles, dict.fromkeys(plugin_ids, "ACTIVE"))
        if not failed and commit is not None:
            try:
                commit(plugin_ids)
            except Exception as error:
                # Nothing was persisted: restore the old config like a setup
                # failure, reported under the target.
                failed = {target: error}
        if failed:
            # New instances that did start may already serve calls; let those
            # finish (bounded) before disposing them.
            loaded = handles
            if timeout := await _seal_and_wait(loaded, steps.calls, drain_timeout):
                errors.append(timeout)
            for handle in reversed(loaded):
                errors.extend(await steps.dispose(handle.record))
            _ = tables.swap(target, *previous)
            restored = await _activate(records, steps, restoring)
            restore_failed = _diverged(records, restored, before)
    finally:
        if retention is not None:
            errors.extend(await retention.release())
    # Both success and rollback replaced the old owners. Publish the settled
    # closure even when the saving caller was cancelled after the drain.
    if on_replaced is not None:
        on_replaced(plugin_ids)
    if failed:
        raise PluginReloadFailed(
            target,
            failed=failed,
            restore_failed=restore_failed,
            cleanup_errors=tuple(errors),
        ) from next(iter(failed.values()))
    return PluginReloadResult(plugin_ids, tuple(errors))


async def _seal_and_wait(
    handles: list[PluginView],
    calls: Callable[[PluginRecord], PluginCallGate | None],
    timeout: float,
) -> PluginReloadTimeout | None:
    """Seals ``handles`` and waits for their admitted calls, up to ``timeout``."""
    gates = {
        handle.plugin_id: gate
        for handle in handles
        if (gate := calls(handle.record)) is not None
    }
    for gate in gates.values():
        gate.seal()
    waiting = asyncio.ensure_future(
        asyncio.gather(*(gate.wait_idle() for gate in gates.values()))
    )
    done, _ = await asyncio.wait({waiting}, timeout=timeout)
    if done:
        return None
    _ = waiting.cancel()
    busy = tuple(pid for pid, gate in gates.items() if gate.in_flight)
    return PluginReloadTimeout(busy, timeout)


async def _activate(
    records: list[PluginRecord], steps: ReloadSteps, reactivating: frozenset[str]
) -> list[PluginView]:
    """Loads the closure in dependency order; returns each record's handle."""
    return [await steps.activate(record, reactivating) for record in records]


def _diverged(
    records: list[PluginRecord],
    handles: list[PluginView],
    expected: Mapping[str, str],
) -> dict[str, BaseException]:
    """Maps each plugin not in its ``expected`` state to the reason, in load order."""
    diverged: dict[str, BaseException] = {}
    for record, handle in zip(records, handles, strict=True):
        plugin_id = record.manifest.id
        state = expected[plugin_id]
        if handle.state == state:
            continue
        diverged[plugin_id] = (
            handle.error
            if handle.error is not None
            else RuntimeError(
                f"插件 {plugin_id} 未能激活"
                if state == "ACTIVE"
                else f"插件 {plugin_id} 未能恢复为 {state}"
            )
        )
    return diverged
