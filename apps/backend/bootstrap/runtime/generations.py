"""Reference-counted runtime versions; publication never cancels their work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.common.task_collector import TaskCollector

if TYPE_CHECKING:
    from bootstrap.channel_host import ChannelHost
    from agent.config_models import Config
    from bootstrap.tools import CoreRuntime


@dataclass(eq=False)
class RuntimeCandidate:
    """Owns prepared resources until publication or explicit discard."""

    generation: int
    core: CoreRuntime
    config: Config
    references: int = 0
    persistent_references: int = 0
    retired: bool = False
    published: bool = False
    closed: bool = False
    drained: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )
    on_closed: Callable[[RuntimeCandidate], None] | None = field(
        default=None, repr=False
    )
    _close_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    channel_host: ChannelHost | None = None
    # Names of the channels this generation carried; fixed once channels are built.
    channel_names: frozenset[str] = frozenset()
    force_close: bool = False
    _work_changed: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )

    def acquire(self, *, persistent: bool = False):
        """Pins this exact version for a request or a detached child operation."""
        if self.closed or (self.retired and not self.references):
            raise RuntimeError("Runtime generation has already retired")
        self.references += 1
        if persistent:
            self.persistent_references += 1
        return RuntimeLease(self, persistent=persistent)

    async def wait_for_work(self) -> None:
        """Waits for accepted operations, excluding idle bridge handler ownership."""
        while self.references > self.persistent_references:
            self._work_changed.clear()
            await self._work_changed.wait()

    def assert_retirable(self) -> None:
        """Checks replacement admission before changing retirement bookkeeping."""
        if self.published and not self.force_close:
            self.core.assert_hot_unloadable()

    async def retire(self) -> None:
        """Stops accepting work and closes only after the final lease exits."""
        self.assert_retirable()
        self.retired = True
        await self.close_if_idle()

    async def close_if_idle(self) -> None:
        """Releases owned resources exactly once when no task retains them."""
        if self._close_task is not None:
            await asyncio.shield(self._close_task)
            return
        if not self.retired or self.references or self.closed:
            return
        self.assert_retirable()
        self.closed = True
        self._close_task = asyncio.create_task(self._close_resources())
        await asyncio.shield(self._close_task)

    async def _close_resources(self) -> None:
        try:
            try:
                await self.core.stop(force=self.force_close or not self.published)
            finally:
                await self.core.memory_runtime.aclose()
        finally:
            self.drained.set()
            if self.on_closed is not None:
                self.on_closed(self)
                self.on_closed = None


class RuntimeLease:
    """A releasable reference to the immutable resources chosen at task start."""

    def __init__(
        self, candidate: RuntimeCandidate, *, persistent: bool = False
    ) -> None:
        self._candidate = candidate
        self._released = False
        self._persistent = persistent

    @property
    def core(self) -> CoreRuntime:
        """Returns the retained core."""
        return self._candidate.core

    @property
    def config(self) -> Config:
        """Returns the retained configuration."""
        return self._candidate.config

    @property
    def generation(self) -> int:
        """Returns the retained generation identifier."""
        return self._candidate.generation

    @property
    def channel_names(self) -> frozenset[str]:
        """Returns the channel names the retained generation was published with."""
        return self._candidate.channel_names

    def retain(self):
        """Pins the same version for child work that can outlive its parent."""
        if self._released:
            raise RuntimeError("Cannot retain a released runtime lease")
        return self._candidate.acquire()

    async def release(self) -> None:
        """Releases ownership without cancelling any other version's work."""
        if self._released:
            return
        self._released = True
        self._candidate.references -= 1
        if self._persistent:
            self._candidate.persistent_references -= 1
        self._candidate._work_changed.set()
        await self._candidate.close_if_idle()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        await self.release()


class GenerationManager:
    """Owns the published pointer, tracked generations and the admission gate."""

    def __init__(self) -> None:
        self.current: RuntimeCandidate | None = None
        self.admission = asyncio.Event()
        self.admission.set()
        self.on_closed: Callable[[RuntimeCandidate], None] | None = None
        self._tracked: list[RuntimeCandidate] = []
        self._retirements = TaskCollector("Retired runtime cleanup")
        self._closed = False

    @property
    def generation(self) -> int:
        """Returns the active version, or zero before startup."""
        return self.current.generation if self.current is not None else 0

    @property
    def tracked(self) -> tuple[RuntimeCandidate, ...]:
        """Returns every generation that has not finished closing its resources."""
        return tuple(self._tracked)

    @property
    def retained(self) -> tuple[RuntimeCandidate, ...]:
        """Returns open resource owners for cross-generation task inspection."""
        return tuple(
            generation for generation in self._tracked if not generation.closed
        )

    @property
    def accepting_work(self) -> bool:
        """Reports whether new user operations can be accepted immediately."""
        return self.admission.is_set() and not self._closed

    @property
    def retirement_errors(self) -> list[Exception]:
        """Returns failures preserved from completed retirement tasks."""
        return self._retirements.errors

    def require_running(self) -> RuntimeCandidate:
        """Returns the published generation, refusing before start and after shutdown."""
        if self.current is None or self._closed:
            raise RuntimeError("Application runtime is not running")
        return self.current

    def acquire(self) -> RuntimeLease:
        """Pins the currently published runtime for one logical operation."""
        return self.require_running().acquire()

    def pin(self) -> RuntimeLease:
        """Retains idle bridge handlers without counting them as accepted work."""
        return self.require_running().acquire(persistent=True)

    async def wait_for_admission(self) -> None:
        """Defers new operations while a process-global channel identity changes."""
        await self.admission.wait()

    def track(self, candidate: RuntimeCandidate) -> None:
        """Registers a generation whose close must be observed before shutdown ends."""
        self._tracked.append(candidate)
        candidate.on_closed = self._candidate_closed

    def start(self, candidate: RuntimeCandidate) -> None:
        """Adopts the first published generation at process start."""
        candidate.published = True
        self.current = candidate
        self.track(candidate)

    def publish(self, candidate: RuntimeCandidate) -> RuntimeCandidate:
        """Swaps the published pointer synchronously and returns the previous owner."""
        previous = self.require_running()
        candidate.published = True
        self.current = candidate
        self.track(candidate)
        return previous

    def retire(self, previous: RuntimeCandidate) -> None:
        """Schedules the replaced generation's close once its accepted work ends."""
        previous.assert_retirable()
        previous.retired = True
        self._retirements.spawn(
            previous.close_if_idle(),
            name=f"runtime:{previous.generation}:retire",
        )

    def close(self) -> None:
        """Refuses new acquisition once process shutdown begins."""
        self._closed = True

    async def close_all(self, *, force: bool = False) -> None:
        """Retires every tracked generation and waits for their resources to close."""
        generations = list(self._tracked)
        if not force:
            for generation in generations:
                generation.core.assert_hot_unloadable()
        for generation in generations:
            generation.force_close = force
            generation.retired = True

        async def close(generation: RuntimeCandidate) -> None:
            await generation.close_if_idle()
            await generation.drained.wait()
            await generation.close_if_idle()

        outcomes = await asyncio.gather(
            *(close(generation) for generation in generations),
            return_exceptions=True,
        )
        errors = [error for error in outcomes if isinstance(error, Exception)]
        if errors:
            raise ExceptionGroup("Runtime generations failed to close", errors)
        await self._retirements.drain()

    def _candidate_closed(self, candidate: RuntimeCandidate) -> None:
        if candidate is not self.current and candidate in self._tracked:
            self._tracked.remove(candidate)
        if self.on_closed is not None:
            self.on_closed(candidate)
