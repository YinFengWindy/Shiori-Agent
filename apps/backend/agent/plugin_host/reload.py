"""In-generation reload of one plugin and the ACTIVE plugins that hard-depend on it.

The kernel decides *which* handles form the closure and owns loading and
disposal; this module owns the transition itself: seal and drain the closure
(abandoning unchanged on timeout or cancellation), then replace it under a
process-resource hold, rolling back to the old config if the new one fails.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from agent.plugin_host.handle import PluginHandle, PluginRecord, PluginState
from agent.plugin_host.process_resources import ResourceRetention
from agent.plugin_host.unload import (
    PluginReloadFailed,
    PluginReloadTimeout,
    PluginReloadUnsupported,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginReloadResult:
    """Outcome of a successful in-generation reload."""

    # Every plugin set up again, target first, in dependency order.
    plugin_ids: tuple[str, ...]
    # Disposal and process-resource close failures; the new instances are ACTIVE.
    cleanup_errors: tuple[BaseException, ...]


@dataclass(frozen=True)
class ReloadSteps:
    """Kernel operations a reload composes; the kernel keeps owning handles."""

    # Disposes one handle and drops it from the kernel; returns cleanup errors.
    dispose: Callable[[PluginHandle], Awaitable[list[Exception]]]
    # Loads one record (after its dependencies) as a reactivation of the given
    # plugin ids; returns the handle it ended up with.
    activate: Callable[[PluginRecord, frozenset[str]], Awaitable[PluginHandle | None]]
    # Holds the plugins' process resources across the swap, when the host has any.
    retain: Callable[[tuple[str, ...]], ResourceRetention | None]


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


def hot_unload_blockers(handles: Iterable[PluginHandle]) -> list[str]:
    """Plugin ids among ``handles`` that declare ``supports_hot_unload: false``."""
    return [
        handle.plugin_id
        for handle in handles
        if not handle.record.manifest.supports_hot_unload
    ]


def refuse_reload(
    plugin_id: str,
    target: PluginHandle | None,
    closure: list[PluginHandle],
    *,
    retired: bool,
) -> None:
    """Rejects reloads only a generation swap (or no reload) may serve."""
    if retired:
        raise PluginReloadUnsupported([plugin_id], "retired")
    if target is None or target.state is not PluginState.ACTIVE:
        disabled = target is not None and target.state is PluginState.DISABLED
        raise PluginReloadUnsupported([plugin_id], "disabled" if disabled else "failed")
    refuse_generation_only(closure)


def refuse_generation_only(closure: list[PluginHandle]) -> None:
    """Rejects closures whose plugins only a generation swap may load or unload."""
    channels = [
        handle.plugin_id
        for handle in closure
        if "channels" in handle.record.manifest.capabilities
        or handle.record.manifest.channels
        or handle.contributions.channels
    ]
    if channels:
        raise PluginReloadUnsupported(channels, "channels")
    if unsafe := hot_unload_blockers(closure):
        raise PluginReloadUnsupported(unsafe, "hot_unload")


async def run_drainers(handles: Iterable[PluginHandle]) -> None:
    """Awaits each handle's ``on_drain`` callbacks in order; a failure propagates."""
    for handle in handles:
        for callback in handle.drainers:
            await callback()


async def reload_closure(
    closure: list[PluginHandle],
    *,
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None = None,
) -> PluginReloadResult:
    """Drains ``closure`` (dependents first, target last), then replaces it.

    Until the drain completes nothing is disposed: a timeout, an ``on_drain``
    failure or caller cancellation reopens every gate and leaves the old
    instances and tables in place. Once draining succeeded the replacement
    runs to completion even if the caller is cancelled meanwhile, including
    ``commit`` (see ``PluginKernel.reload``).
    """
    await _drain(closure, drain_timeout)
    plugin_ids = frozenset(handle.plugin_id for handle in closure)
    replacement = asyncio.create_task(
        _replace(
            closure,
            values=values,
            raw_values=raw_values,
            tables=tables,
            steps=steps,
            drain_timeout=drain_timeout,
            commit=commit,
            reactivating=plugin_ids,
            restoring=plugin_ids,
            strict=True,
        )
    )
    return await _run_to_completion(replacement)


async def toggle_closure(
    closure: list[PluginHandle],
    *,
    enabled: bool,
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None = None,
) -> PluginReloadResult:
    """Loads (``enabled``) or unloads ``closure`` (dependents first, target last).

    Nothing is drained: disabling cancels in-flight work, as a generation swap
    does. The closure is disposed and loaded again under the new tables, which
    leaves disabled plugins DISABLED or BLOCKED and enabled ones ACTIVE, or
    FAILED when their setup fails (kept, as a generation swap would). Only a
    failing ``commit`` restores the previous tables and states. Runs to
    completion even if the caller is cancelled (see ``PluginKernel.set_enabled``).
    """
    replacement = asyncio.create_task(
        _replace(
            closure,
            values=values,
            raw_values=raw_values,
            tables=tables,
            steps=steps,
            drain_timeout=drain_timeout,
            commit=commit,
            # Neither a newly enabled plugin nor one turned off was active
            # right before this setup; a restored one was.
            reactivating=frozenset(),
            restoring=(
                frozenset()
                if enabled
                else frozenset(handle.plugin_id for handle in closure)
            ),
            strict=False,
        )
    )
    return await _run_to_completion(replacement)


async def _drain(closure: list[PluginHandle], timeout: float) -> None:
    """Drains the closure stage by stage, dependents first.

    Each stage seals one plugin, waits for its admitted calls and runs its
    ``on_drain``; its providers stay open meanwhile, so a dependent's accepted
    work can still call them (and those calls are waited for when the provider
    is sealed in turn).

    When the drain is abandoned (timeout, ``on_drain`` failure, cancellation)
    every instance stays as it was: ``on_drain`` of stages that already
    finished has run, which is harmless because ``on_drain`` only waits for
    accepted work, and an ``on_drain`` still in progress finishes in the
    background.
    """
    current: list[PluginHandle] = []
    abandoned = False

    async def staged() -> None:
        for handle in closure:
            if abandoned:
                return
            current[:] = [handle]
            handle.calls.seal()
            await handle.calls.wait_idle()
            if abandoned:
                return
            await run_drainers((handle,))
        current.clear()

    # Waiting runs as its own task that is never cancelled: on_drain callbacks
    # may await (gather) the plugin's own work, and cancelling them would
    # cancel that work, while an abandoned reload must leave it running.
    waiting = asyncio.create_task(staged())
    try:
        done, _ = await asyncio.wait({waiting}, timeout=timeout)
        if not done:
            raise PluginReloadTimeout(
                tuple(handle.plugin_id for handle in current), timeout
            )
        waiting.result()
    except BaseException:
        # Stop the remaining stages before reopening what was sealed so far.
        abandoned = True
        _reopen(closure)
        waiting.add_done_callback(_log_abandoned_drain)
        raise


def _log_abandoned_drain(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("已放弃的插件重载排空以异常结束", exc_info=error)


def _reopen(closure: list[PluginHandle]) -> None:
    for handle in closure:
        handle.calls.reopen()


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
    closure: list[PluginHandle],
    *,
    values: dict[str, Any],
    raw_values: dict[str, Any],
    tables: ConfigTables,
    steps: ReloadSteps,
    drain_timeout: float,
    commit: Callable[[tuple[str, ...]], None] | None,
    reactivating: frozenset[str],
    restoring: frozenset[str],
    strict: bool,
) -> PluginReloadResult:
    """Disposes ``closure`` and loads it again under the new tables.

    ``reactivating`` / ``restoring`` name the plugins whose setup sees
    ``was_active`` when loading the new / restoring the old tables. With
    ``strict`` a plugin that does not become ACTIVE fails the transition like
    a failing ``commit``; a failed transition restores every closure plugin to
    its previous state.
    """
    target = closure[-1].plugin_id
    records = [handle.record for handle in reversed(closure)]
    plugin_ids = tuple(record.manifest.id for record in records)
    before = {handle.plugin_id: handle.state for handle in closure}
    retention = steps.retain(plugin_ids)
    errors: list[BaseException] = []
    failed: dict[str, BaseException] = {}
    restore_failed: dict[str, BaseException] = {}
    try:
        for handle in closure:
            errors.extend(await steps.dispose(handle))
        previous = tables.swap(target, values, raw_values)
        handles = await _activate(records, steps, reactivating)
        if strict:
            failed = _diverged(
                records, handles, dict.fromkeys(plugin_ids, PluginState.ACTIVE)
            )
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
            loaded = [handle for handle in handles if handle is not None]
            if timeout := await _seal_and_wait(loaded, drain_timeout):
                errors.append(timeout)
            for handle in reversed(loaded):
                errors.extend(await steps.dispose(handle))
            _ = tables.swap(target, *previous)
            restored = await _activate(records, steps, restoring)
            restore_failed = _diverged(records, restored, before)
    finally:
        if retention is not None:
            errors.extend(await retention.release())
    if failed:
        raise PluginReloadFailed(
            target,
            failed=failed,
            restore_failed=restore_failed,
            cleanup_errors=tuple(errors),
        ) from next(iter(failed.values()))
    return PluginReloadResult(plugin_ids, tuple(errors))


async def _seal_and_wait(
    handles: list[PluginHandle], timeout: float
) -> PluginReloadTimeout | None:
    """Seals ``handles`` and waits for their admitted calls, up to ``timeout``."""
    for handle in handles:
        handle.calls.seal()
    waiting = asyncio.ensure_future(
        asyncio.gather(*(handle.calls.wait_idle() for handle in handles))
    )
    done, _ = await asyncio.wait({waiting}, timeout=timeout)
    if done:
        return None
    _ = waiting.cancel()
    busy = tuple(handle.plugin_id for handle in handles if handle.calls.in_flight)
    return PluginReloadTimeout(busy, timeout)


async def _activate(
    records: list[PluginRecord], steps: ReloadSteps, reactivating: frozenset[str]
) -> list[PluginHandle | None]:
    """Loads the closure in dependency order; returns each record's handle."""
    return [await steps.activate(record, reactivating) for record in records]


def _diverged(
    records: list[PluginRecord],
    handles: list[PluginHandle | None],
    expected: dict[str, PluginState],
) -> dict[str, BaseException]:
    """Maps each plugin not in its ``expected`` state to the reason, in load order."""
    diverged: dict[str, BaseException] = {}
    for record, handle in zip(records, handles, strict=True):
        plugin_id = record.manifest.id
        state = expected[plugin_id]
        if handle is not None and handle.state is state:
            continue
        diverged[plugin_id] = (
            handle.error
            if handle is not None and handle.error is not None
            else RuntimeError(
                f"插件 {plugin_id} 未能激活"
                if state is PluginState.ACTIVE
                else f"插件 {plugin_id} 未能恢复为 {state.name}"
            )
        )
    return diverged
