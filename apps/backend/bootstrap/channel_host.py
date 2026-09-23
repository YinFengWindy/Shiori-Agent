from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal, NotRequired, TypedDict

from core.common.task_collector import TaskCollector
from infra.channels.contract import (
    Channel,
    ChannelContext,
    ChannelStatus,
    SupportsChannelStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelFailure:
    """Describes a channel that could not be constructed or started."""

    channel: str
    phase: str
    error_type: str
    message: str


class ChannelHandoverError(RuntimeError):
    """A failed channel switch, including any connections that could not recover."""

    def __init__(self, failure: ChannelFailure, degraded: list[ChannelFailure]) -> None:
        self.failure = failure
        self.degraded = degraded
        super().__init__(
            f"Channel {failure.channel} {failure.phase} failed: {failure.message}"
        )

    def to_details(self):
        """Returns actionable connection status without reporting successful rollback."""
        from dataclasses import asdict

        return {
            "failure": asdict(self.failure),
            "degraded": [asdict(item) for item in self.degraded],
        }


class ChannelSnapshot(TypedDict):
    """Host-side state of one registered or failed channel."""

    state: Literal["active", "failed"]
    error: str
    status: NotRequired[ChannelStatus]


def _failure(name: str, phase: str, error: BaseException) -> ChannelFailure:
    return ChannelFailure(name, phase, type(error).__name__, str(error))


class ChannelHost:
    def __init__(
        self,
        ctx_factory: Callable[[Channel], ChannelContext],
        *,
        transport_lock: asyncio.Lock | None = None,
    ) -> None:
        self._ctx_factory = ctx_factory
        self._channels: list[Channel] = []
        self._failures: list[ChannelFailure] = []
        self._configurations: dict[str, object] = {}
        self._transport_lock = transport_lock or asyncio.Lock()
        self._retired_transports: dict[str, Channel] = {}
        self._retirements = TaskCollector("Channel retirement")

    def add(self, channel: Channel, *, configuration: object = None) -> None:
        """Registers one candidate without starting it or binding subscribers."""
        if any(item.name == channel.name for item in self._channels):
            raise ValueError(f"Duplicate channel name: {channel.name}")
        self._channels.append(channel)
        self._configurations[channel.name] = configuration

    def reusable(self, name: str, configuration: object) -> Channel | None:
        """Returns an existing connection when its effective configuration is unchanged."""
        if self._configurations.get(name) != configuration:
            return None
        return next(
            (channel for channel in self._channels if channel.name == name), None
        )

    def requires_exclusive_handover(self, candidate: ChannelHost) -> bool:
        """Requires accepted work to drain before a channel name changes connection."""
        existing = {channel.name: channel for channel in self._channels}
        existing.update(self._retired_transports)
        return any(
            channel.name in existing and existing[channel.name] is not channel
            for channel in candidate.channels
        )

    def pause_intake(self) -> None:
        """Closes channel admission while existing replies drain on their credentials."""
        paused = []
        try:
            for channel in self._channels:
                channel.pause_intake()
                paused.append(channel)
        except BaseException:
            for channel in reversed(paused):
                channel.resume_intake()
            raise

    def resume_intake(self) -> None:
        """Reopens the currently published connections after a replacement attempt."""
        for channel in self._channels:
            channel.resume_intake()

    async def handover(
        self,
        candidate: ChannelHost,
        *,
        commit: Callable[[], None] | None = None,
        retire_after: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Switches changed connections under the send barrier and rolls back failures."""
        async with self._transport_lock:
            parked = await self.handover_channels(
                candidate,
                commit=commit,
                retain_removed=retire_after is not None,
            )
            if parked and retire_after is not None:
                for channel in parked:
                    self._retired_transports[channel.name] = channel
                    self._ctx_factory(channel).push_tool.retire_channel(channel.name)
                self._retirements.spawn(
                    self._retire_transports(parked, retire_after),
                    name="channel-retire",
                )

    async def handover_channels(
        self,
        candidate: ChannelHost,
        *,
        commit: Callable[[], None] | None = None,
        retain_removed: bool = False,
    ) -> list[Channel]:
        """Transfers connection ownership; callers must hold the transport barrier."""
        candidate_names = {channel.name for channel in candidate.channels}
        retired_replaced = [
            channel
            for name, channel in self._retired_transports.items()
            if name in candidate_names
        ]
        removed = [
            channel for channel in self._channels if channel not in candidate.channels
        ]
        removed.extend(retired_replaced)
        parked = [
            channel
            for channel in removed
            if retain_removed and channel.name not in candidate_names
        ]
        for channel in parked:
            if not callable(getattr(channel, "pause_intake", None)) or not callable(
                getattr(channel, "resume_intake", None)
            ):
                raise ValueError(
                    f"Channel {channel.name} does not support draining removal"
                )
        added = [
            channel for channel in candidate.channels if channel not in self._channels
        ]
        stopped = []
        attempted = []
        current_name = "configuration"
        phase = "stop"
        try:
            for channel in reversed(removed):
                current_name = channel.name
                if channel in parked:
                    channel.pause_intake()
                    continue
                await channel.stop()
                stopped.append(channel)
            phase = "start"
            for channel in added:
                current_name = channel.name
                attempted.append(channel)
                await channel.start(
                    replace(candidate._ctx_factory(channel), intake_paused=True)
                )
            phase = "resume"
            for channel in candidate.channels:
                current_name = channel.name
                channel.resume_intake()
            # Intake callbacks cannot run on this loop between synchronous resume
            # and publication; any activation failure still precedes persistence.
            phase = "commit"
            current_name = "configuration"
            if commit is not None:
                commit()
        except BaseException as error:
            failure = _failure(current_name, phase, error)
            degraded = []
            # Cancel admission scheduled by a pre-commit resume before cleanup yields.
            for channel in attempted:
                try:
                    channel.pause_intake()
                except BaseException as pause_error:
                    degraded.append(
                        _failure(channel.name, "candidate_pause", pause_error)
                    )
            # A failed stop has uncertain external state; do not create a duplicate connection.
            if phase == "stop":
                degraded.append(failure)
            for channel in reversed(attempted):
                try:
                    await channel.stop()
                except BaseException as cleanup_error:
                    degraded.append(
                        _failure(channel.name, "candidate_cleanup", cleanup_error)
                    )
            unsafe_names = {item.channel for item in degraded}
            for channel in reversed(stopped):
                if channel.name in unsafe_names:
                    continue
                try:
                    await channel.start(self._ctx_factory(channel))
                    if channel in retired_replaced:
                        channel.pause_intake()
                        self._ctx_factory(channel).push_tool.retire_channel(
                            channel.name
                        )
                except BaseException as restore_error:
                    degraded.append(_failure(channel.name, "restore", restore_error))
            unsafe_names = {item.channel for item in degraded}
            for channel in self._channels:
                if channel.name in unsafe_names:
                    continue
                try:
                    channel.resume_intake()
                except BaseException as resume_error:
                    degraded.append(_failure(channel.name, "resume", resume_error))
            self._failures.extend(degraded)
            if isinstance(
                error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
            ):
                raise
            if phase == "commit" and not degraded:
                raise
            raise ChannelHandoverError(failure, degraded) from error
        self._channels = candidate.channels
        self._configurations = dict(candidate._configurations)
        self._ctx_factory = candidate._ctx_factory
        self._failures = candidate.failures
        for channel in retired_replaced:
            self._retired_transports.pop(channel.name, None)
        return parked

    async def _retire_transports(self, channels, ready) -> None:
        await ready()
        async with self._transport_lock:
            for channel in channels:
                if self._retired_transports.get(channel.name) is not channel:
                    continue
                try:
                    await channel.stop()
                except Exception as error:
                    self.record_failure(channel.name, phase="retire", error=error)
                    raise
                self._retired_transports.pop(channel.name, None)

    def record_failure(self, channel: str, *, phase: str, error: BaseException) -> None:
        """Records a channel failure while allowing independent channels to proceed."""

        self._failures.append(
            ChannelFailure(
                channel=str(channel),
                phase=str(phase),
                error_type=type(error).__name__,
                message=str(error),
            )
        )

    async def start_all(self) -> None:
        for channel in self._channels:
            try:
                await channel.start(self._ctx_factory(channel))
                logger.info("渠道已启动: %s", channel.name)
            except Exception as e:
                self.record_failure(channel.name, phase="start", error=e)
                logger.error("渠道启动失败 %s: %s", channel.name, e)

    async def stop_all(self) -> None:
        self._retirements.cancel_all()
        await self._retirements.drain()
        for channel in reversed([*self._channels, *self._retired_transports.values()]):
            try:
                await channel.stop()
            except Exception as e:
                logger.warning("渠道停止失败 %s: %s", channel.name, e)

    @property
    def channels(self) -> list[Channel]:
        return list(self._channels)

    def snapshot(self) -> dict[str, ChannelSnapshot]:
        """Returns each registered or failed channel's state, keyed by channel name.

        A recorded failure wins over registration: ``start_all`` keeps a channel
        whose start failed. Only the latest failure per name is reported. The
        optional ``status()`` of a healthy channel is included verbatim; if it
        raises, the channel is reported failed instead of hiding the error.
        """
        latest = {failure.channel: failure for failure in self._failures}
        result: dict[str, ChannelSnapshot] = {
            name: {"state": "failed", "error": _describe_failure(failure)}
            for name, failure in latest.items()
        }
        for channel in self._channels:
            if channel.name in latest:
                continue
            entry: ChannelSnapshot = {"state": "active", "error": ""}
            if isinstance(channel, SupportsChannelStatus):
                try:
                    entry["status"] = channel.status()
                except Exception as error:
                    logger.warning("渠道状态读取失败 %s: %s", channel.name, error)
                    entry = {
                        "state": "failed",
                        "error": _describe_failure(
                            _failure(channel.name, "status", error)
                        ),
                    }
            result[channel.name] = entry
        return result

    @property
    def failures(self) -> list[ChannelFailure]:
        """Returns a snapshot of channel construction/start failures."""

        return list(self._failures)


def _describe_failure(failure: ChannelFailure) -> str:
    return f"{failure.phase}: {failure.error_type}: {failure.message}"
