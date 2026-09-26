"""Prepare/publish protocol used by the settings transaction boundary."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from agent.config_models import Config
from bootstrap.runtime.events import RuntimeEventBus
from bootstrap.runtime.generations import RuntimeCandidate
from bootstrap.tools import build_core_runtime
from bootstrap.channels import start_channels
from bootstrap.runtime.memory import validate_memory_transition
from bootstrap.runtime.construction import prepare_core_runtime
from bootstrap.runtime.channel_barrier import channel_handover_barrier


class RuntimeReloadMixin:
    """Owns configuration publication without restarting the application."""

    @property
    def generation(self) -> int:
        """Returns the active version, or zero before startup."""
        return self._generation_manager.generation

    @property
    def retained_generations(self):
        """Returns active resource owners for cross-generation task inspection."""
        return self._generation_manager.retained

    @property
    def accepting_work(self) -> bool:
        """Reports whether new user operations can be accepted immediately."""
        return self._generation_manager.accepting_work

    def acquire(self):
        """Pins the currently published runtime for one logical operation."""
        return self._generation_manager.acquire()

    def pin(self):
        """Retains idle bridge handlers without counting them as accepted work."""
        return self._generation_manager.pin()

    async def wait_for_admission(self) -> None:
        """Defers new operations while a process-global channel identity changes."""
        await self._generation_manager.wait_for_admission()

    async def prepare(self, config: Config) -> RuntimeCandidate:
        """Prepares isolated capabilities while the active runtime stays available."""
        current = self._generation_manager.require_running()
        if config == self.config:
            return current
        current.core.assert_hot_unloadable()
        validate_memory_transition(self.config, config, self.workspace)
        snapshot = deepcopy(config)
        core = await prepare_core_runtime(
            snapshot,
            self.workspace,
            self.http_resources,
            builder=build_core_runtime,
            shared=self.core,
            event_bus=RuntimeEventBus(self.event_bus),
            event_outlet=self.event_bus,
            agent_loop_provider=lambda: self._dispatcher,
        )
        candidate = RuntimeCandidate(self.generation + 1, core, snapshot)
        try:
            await core.start()
            self._prepare_background(candidate)
            plugins = core.plugin_manager
            candidate.channel_host = await start_channels(
                bus=self.bus,
                session_manager=self.session_manager,
                push_tool=self.push_tool,
                http_resources=self.http_resources,
                event_bus=self.event_bus,
                interrupt_controller=self._dispatcher,
                bot_commands=plugins.bot_commands if plugins else None,
                plugin_channels=plugins.channels if plugins else None,
                enable_message_channels=self.features.enable_message_channels,
                previous_host=self.channel_host,
                channel_directory=core.channel_directory,
            )
            candidate.channel_names = frozenset(
                channel.name for channel in candidate.channel_host.channels
            )
        except BaseException:
            self._discard_background(candidate)
            await candidate.retire()
            raise
        return candidate

    async def publish(
        self,
        candidate: RuntimeCandidate,
        commit: Callable[[], None] | None = None,
    ) -> None:
        """Commits persistence immediately before publishing the prepared pointer."""
        current = self._generation_manager.require_running()
        if candidate is current:
            if commit is not None:
                commit()
            return
        if (
            candidate.closed
            or candidate.published
            or candidate.generation != self.generation + 1
        ):
            raise RuntimeError("Runtime candidate is stale or already consumed")
        current.core.assert_hot_unloadable()
        if self.channel_host is None or candidate.channel_host is None:
            self._publish_pointer(candidate, commit)
            return
        async with channel_handover_barrier(
            self.channel_host,
            candidate,
            current=current,
            accepted=self._generation_manager.tracked,
            background_groups=self._background_groups,
            admission=self._generation_manager.admission,
            drain_outbound=self.bus.drain_outbound,
            restore_background=lambda: self._restore_background(current),
        ) as accepted_generations:
            await self.channel_host.handover(
                candidate.channel_host,
                commit=lambda: self._publish_pointer(candidate, commit),
                retire_after=lambda: self._retire_transports(accepted_generations),
            )

    async def discard(self, candidate: RuntimeCandidate) -> None:
        """Closes an unpublished candidate after failed preparation or persistence."""
        if candidate.published:
            return
        self._discard_background(candidate)
        await candidate.retire()

    def _publish_pointer(
        self, candidate: RuntimeCandidate, commit: Callable[[], None] | None
    ) -> None:
        """Runs durable commit and pointer publication in one synchronous step."""
        self._generation_manager.require_running().core.assert_hot_unloadable()
        validate_memory_transition(self.config, candidate.config, self.workspace)
        if commit is not None:
            commit()
        if candidate.core.plugin_manager is not None:
            candidate.core.plugin_manager.publish_accounts()
        previous = self._generation_manager.publish(candidate)
        self.config = candidate.config
        self.core = candidate.core
        self._publish_background(previous, candidate)
        # No await separates durable commit and pointer publication.
        self._generation_manager.retire(previous)

    def _restore_background(self, current: RuntimeCandidate) -> None:
        """Re-arms the active generation's scheduling after a failed handover."""
        try:
            self._prepare_background(current)
            self._publish_background(None, current)
        except BaseException as error:
            try:
                self._discard_background(current)
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "Background recovery failed", [error, cleanup_error]
                ) from error
            raise

    async def _retire_transports(self, accepted: tuple[RuntimeCandidate, ...]) -> None:
        """Releases replaced transports only after their accepted replies drain."""
        for generation in accepted:
            await generation.drained.wait()
        await self.bus.drain_outbound()
