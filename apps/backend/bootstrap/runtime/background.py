"""Handoff of proactive scheduling between runtime versions.

Background loops only do work the next generation redoes on its own
schedule (proactive ticks), so replacing a version
interrupts their in-flight work instead of waiting for it: a model call stuck
in retries must never hold a settings switch or shutdown.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Protocol

from bootstrap.proactive import build_proactive_runtime
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime
from core.scene.host import HostSceneAdapter
from shiori_sdk.core.scene import SCENE_HOST


class _Stoppable(Protocol):
    def stop(self) -> None: ...


class RuntimeBackground:
    """Prepares background work without starting it or mutating live scheduling."""

    def __init__(self, app, candidate: RuntimeCandidate) -> None:
        core = candidate.core
        config = candidate.config
        self.candidate = candidate
        self._plugins = getattr(core, "plugin_manager", None)
        self._loops: list[_Stoppable] = []
        self._coroutines: list[Coroutine[Any, Any, None]] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._runner: asyncio.Task[None] | None = None
        self._stopped = False
        self.proactive_loops = {}
        if app.features.enable_proactive and config.model_registrations:
            manager = core.plugin_manager
            if manager is None:
                # Proactive tool calls must pass this generation's core checks
                # (workspace guard included); never fall back to a bare kernel.
                raise RuntimeError("主动循环需要本代插件内核，但运行时没有插件内核")
            plugins = manager
            tasks, self.proactive_loops = build_proactive_runtime(
                config,
                app.workspace,
                session_manager=core.session_manager,
                provider=core.provider,
                light_provider=core.light_provider,
                push_tool=core.push_tool,
                memory_store=core.memory_runtime,
                presence=core.presence,
                agent_loop=core.loop,
                # Read the kernel live so plugins unloaded or loaded within this
                # generation take effect on the next tool call or tick.
                kernel=lambda: plugins.kernel,
                proactive_motives=core.proactive_motives,
                event_bus=core.event_bus,
                provider_consumer=core.additional_providers.append,
                proactive_host=core.proactive_host,
                group_environment=core.group_environment,
            )
            self._coroutines.extend(tasks)
            self._loops.extend(self.proactive_loops.values())

    def start(self, previous: RuntimeBackground | None = None) -> None:
        """Transfers scheduling once the stopped previous group has unwound.

        Starting only after ``previous`` drains keeps two generations' loops
        from touching the same memory and proactive state concurrently.
        """
        if self._plugins is not None:
            # Scene intake waits for publication; later in-generation loads
            # of the scene plugin start at once (``SceneHost.on_published``).
            host = self._plugins.kernel.get(SCENE_HOST)
            if isinstance(host, HostSceneAdapter):
                host.publish()
        if not self._coroutines:
            return
        lease = self.candidate.acquire()

        async def run() -> None:
            try:
                if previous is not None:
                    await previous.drain()
                if self._stopped:
                    self.discard()
                    return
                with bind_runtime(lease):
                    self._tasks = [
                        asyncio.create_task(
                            task,
                            name=f"runtime:{self.candidate.generation}:background:{index}",
                        )
                        for index, task in enumerate(self._coroutines)
                    ]
                    self._coroutines = []
                    if self._tasks:
                        await self._join_tasks()
            finally:
                self.discard()
                await lease.release()

        self._runner = asyncio.create_task(
            run(), name=f"runtime:{self.candidate.generation}:background"
        )

    def stop(self) -> None:
        """Closes admission and cancels in-flight background work.

        Loops are told to stop first so none schedules another round while its
        task unwinds; ``drain`` then waits for the cancellation to finish.
        """
        self._stopped = True
        for loop in self._loops:
            loop.stop()
        for task in self._tasks:
            task.cancel()

    async def drain(self) -> None:
        """Waits until the background work and all its owned polling have ended."""
        if self._runner is not None:
            await asyncio.shield(self._runner)

    async def _join_tasks(self) -> None:
        """Waits for every loop; only the cancellation ``stop`` requested is expected.

        A loop that ends cancelled without ``stop`` leaked a cancellation from
        inside its work, so it is reported like any other failure.
        """
        outcomes = await asyncio.gather(*self._tasks, return_exceptions=True)
        errors = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, BaseException)
            and not (self._stopped and isinstance(outcome, asyncio.CancelledError))
        ]
        if errors:
            raise BaseExceptionGroup("Background runtime work failed", errors)

    def discard(self) -> None:
        """Closes prepared coroutine objects that were never scheduled."""
        for coroutine in self._coroutines:
            coroutine.close()
        self._coroutines = []


class RuntimeBackgroundMixin:
    """Coordinates background ownership alongside AppRuntime publication."""

    def _prepare_background(self, candidate: RuntimeCandidate) -> None:
        self._background_groups[candidate] = RuntimeBackground(self, candidate)

    def _generation_closed(self, candidate: RuntimeCandidate) -> None:
        self._background_groups.pop(candidate, None)

    def _publish_background(self, previous, candidate: RuntimeCandidate) -> None:
        old_group = self._background_groups.get(previous)
        if old_group is not None:
            old_group.stop()
        group = self._background_groups[candidate]
        if candidate.core.scene_followup_subscription is not None:
            candidate.core.scene_followup_subscription.start()
        self.proactive_loops = group.proactive_loops
        group.start(old_group)

    def _discard_background(self, candidate: RuntimeCandidate) -> None:
        group = self._background_groups.pop(candidate, None)
        if group is not None:
            group.discard()

    async def _stop_background(self) -> None:
        groups = list(self._background_groups.values())
        for group in groups:
            group.stop()
        results = await asyncio.gather(
            *(group.drain() for group in groups), return_exceptions=True
        )
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("Background runtime shutdown failed", errors)
