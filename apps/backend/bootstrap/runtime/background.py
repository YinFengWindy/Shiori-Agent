"""Graceful handoff of proactive and optimizer scheduling between versions."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Protocol

from bootstrap.proactive import build_memory_optimizer_task, build_proactive_runtime
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime


class _Stoppable(Protocol):
    def stop(self) -> None: ...


class RuntimeBackground:
    """Prepares background work without starting it or mutating live scheduling."""

    def __init__(self, app, candidate: RuntimeCandidate) -> None:
        core = candidate.core
        config = candidate.config
        self.candidate = candidate
        self._scene = getattr(core, "scene_service", None)
        self._loops: list[_Stoppable] = []
        self._coroutines: list[Coroutine[Any, Any, None]] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._runner: asyncio.Task[None] | None = None
        self._stopped = False
        self.proactive_loops = {}
        tasks, self.optimizer = build_memory_optimizer_task(
            config,
            provider=core.provider,
            memory_store=core.memory_runtime.markdown.store,
            role_runtime_registry=core.role_runtime_registry,
            loop_consumer=self._loops.append,
        )
        self._coroutines.extend(tasks)
        core.memory_optimizer = self.optimizer
        if app.features.enable_proactive and config.model_registrations:
            manager = core.plugin_manager
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
                tool_hooks=list(manager.tool_hooks) if manager else None,
                proactive_gates=list(manager.proactive_gates) if manager else None,
                proactive_motives=core.proactive_motives,
                event_bus=core.event_bus,
                provider_consumer=core.additional_providers.append,
                desktop_presence=app.desktop_presence,
            )
            self._coroutines.extend(tasks)
            self._loops.extend(self.proactive_loops.values())

    def start(self, previous: RuntimeBackground | None = None) -> None:
        """Transfers scheduling only after the previous accepted work finishes."""
        if self._scene is not None:
            self._scene.activate()
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
                        await asyncio.gather(*self._tasks)
            finally:
                self.discard()
                await lease.release()

        self._runner = asyncio.create_task(
            run(), name=f"runtime:{self.candidate.generation}:background"
        )

    def stop(self) -> None:
        """Closes admission and wakes sleepers without cancelling accepted work."""
        self._stopped = True
        for loop in self._loops:
            loop.stop()

    async def drain(self) -> None:
        """Waits for the accepted background work and all its owned polling."""
        if self._runner is not None:
            await asyncio.shield(self._runner)

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
        self._memory_optimizer = group.optimizer
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
