"""Prepare/publish protocol used by the settings transaction boundary."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from functools import partial
import logging

from agent.config_models import Config
from agent.plugin_host.handle import PluginRecord
from bootstrap.runtime.events import RuntimeEventBus
from bootstrap.runtime.generations import RuntimeCandidate, RuntimeRetention
from bootstrap.tools import build_core_runtime
from bootstrap.channels import start_channels
from conversation.commands import command_menu
from core.accounts.plugin_capability import publish_plugin_accounts
from core.channels.plugin_capability import active_plugin_channels
from bootstrap.runtime.construction import prepare_core_runtime
from bootstrap.runtime.channel_barrier import channel_handover_barrier

logger = logging.getLogger(__name__)


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

    async def prepare(
        self,
        config: Config,
        *,
        plugin_discovery_snapshot: list[PluginRecord] | None = None,
    ) -> RuntimeCandidate:
        """Prepares isolated capabilities while the active runtime stays available."""
        current = self._generation_manager.require_running()
        if config == self.config and plugin_discovery_snapshot is None:
            return current
        current.core.assert_hot_unloadable()
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
            process_resources=self._plugin_process_resources,
            background_result_runner=self._dispatcher.process_background_result,
            plugin_discovery_snapshot=plugin_discovery_snapshot,
            published_runtime=lambda: self,
        )
        candidate = RuntimeCandidate(self.generation + 1, core, snapshot)
        try:
            await core.start()
            self._prepare_background(candidate)
            plugins = core.plugin_manager
            candidate.channel_host = await start_channels(
                bus=self.bus,
                session_manager=self.session_manager,
                http_resources=self.http_resources,
                event_bus=self.event_bus,
                interrupt_controller=self._dispatcher,
                bot_commands=command_menu(plugins.kernel) if plugins else None,
                plugin_channels=active_plugin_channels(plugins) if plugins else None,
                enable_message_channels=self.features.enable_message_channels,
                previous_host=self.channel_host,
                channel_directory=core.channel_directory,
                role_store=core.role_runtime_registry.repository.store,
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
        """Replace a runtime after cancelling its pending channel reply suffixes."""
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
        accepted = self._generation_manager.tracked
        for generation in accepted:
            generation.reply_sequences.stop()
        try:
            await self._publish_candidate(candidate, commit)
        finally:
            if not candidate.published:
                for generation in accepted:
                    generation.reply_sequences.resume()

    async def _publish_candidate(
        self,
        candidate: RuntimeCandidate,
        commit: Callable[[], None] | None = None,
    ) -> None:
        """Commits persistence immediately before publishing the prepared pointer."""
        current = self._generation_manager.require_running()
        if self.channel_host is None or candidate.channel_host is None:
            self._publish_pointer(candidate, commit)
            await self._drain_plugin_process_resources()
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
            retained = (
                RuntimeRetention(accepted_generations)
                if self.channel_host.removes_channels(candidate.channel_host)
                else None
            )
            transferred = False
            try:
                transferred = await self.channel_host.handover(
                    candidate.channel_host,
                    commit=lambda: self._publish_pointer(candidate, commit),
                    retire_after=(
                        partial(self._retire_transports, retained) if retained else None
                    ),
                    retire_complete=retained.release if retained else None,
                )
            finally:
                if retained is not None and not transferred:
                    await retained.release()
        await self._drain_plugin_process_resources()

    async def _drain_plugin_process_resources(self) -> None:
        """A cleanup failure after publication cannot roll back committed settings."""
        try:
            await self._plugin_process_resources.drain()
        except Exception as error:
            self._cleanup_errors.append(error)
            logger.error("Published plugin resource cleanup failed", exc_info=error)

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
        if commit is not None:
            commit()
        if candidate.core.plugin_manager is not None:
            publish_plugin_accounts(candidate.core.plugin_manager.kernel)
        previous = self._generation_manager.publish(candidate)
        self.config = candidate.config
        self.core = candidate.core
        if candidate.core.plugin_manager is not None:
            self._plugin_process_resources.publish(
                candidate.core.plugin_manager.namespace
            )
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

    async def _retire_transports(self, retained: RuntimeRetention) -> None:
        """Drains removed connections' replies without disposing their capabilities."""
        from core.common.cleanup import run_cleanup_steps

        await run_cleanup_steps(
            ("runtime_work.drain", retained.drain),
            ("outbound.drain", self.bus.drain_outbound),
            aggregate_errors=True,
        )
