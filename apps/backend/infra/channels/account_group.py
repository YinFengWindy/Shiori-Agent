"""One host channel whose per-account member channels start and stop at runtime."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, runtime_checkable, Protocol

if TYPE_CHECKING:
    from shiori_sdk.channels import Channel, ChannelContext

logger = logging.getLogger(__name__)


@runtime_checkable
class SupportsMemberChannels(Protocol):
    """A channel that hosts further, separately named channels.

    The host resolves channel-name lookups (stream support, prompt hints,
    default chat type) through ``member_channel`` when no top-level channel
    carries the name.
    """

    def member_channel(self, name: str) -> Channel | None: ...

    def member_channels(self) -> list[Channel]: ...


class AccountChannelGroup:
    """Hosts one member channel per account under a single registered channel.

    Channels are fixed when a runtime generation starts, but accounts are
    created, connected and deleted through plugin RPCs without reloading the
    runtime. The plugin registers this group once; members keep their own
    names (so session keys stay per account) and are started with the
    group's context when added and stopped when removed. The group is rebuilt
    with every plugin generation, never reused across generations.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._members: dict[str, Channel] = {}
        self._ctx: ChannelContext | None = None
        self._paused = False

    @property
    def configuration_key(self) -> None:
        """Its members belong to one plugin generation, so it is never reused."""
        return None

    def member(self, key: str) -> Channel | None:
        """Returns the member channel added under ``key``."""
        return self._members.get(key)

    def member_channel(self, name: str) -> Channel | None:
        """Returns the member channel carrying the transport name ``name``."""
        return next(
            (channel for channel in self._members.values() if channel.name == name),
            None,
        )

    def member_channels(self) -> list[Channel]:
        """Returns every member channel, e.g. for the host's channel status list."""
        return list(self._members.values())

    async def add(self, key: str, channel: Channel) -> None:
        """Adds one account's channel, starting it at once if the group runs.

        A start failure propagates to the caller with the member kept, so it
        is stopped with the group; the member reports its own account state.
        """
        if key in self._members:
            raise ValueError(f"Duplicate account channel: {key}")
        self._members[key] = channel
        if self._ctx is not None:
            await channel.start(replace(self._ctx, intake_paused=self._paused))

    async def remove(self, key: str) -> Channel | None:
        """Removes one account's channel, stopping it if the group runs."""
        channel = self._members.pop(key, None)
        if channel is not None and self._ctx is not None:
            await channel.stop()
        return channel

    async def start(self, ctx: ChannelContext) -> None:
        """Starts every member; one account failing leaves the others running."""
        self._ctx = ctx
        self._paused = ctx.intake_paused
        for channel in list(self._members.values()):
            try:
                await channel.start(ctx)
            except Exception:
                # Boundary: each account is independent and reports its own
                # failure to the host; the group itself stays up.
                logger.exception("账号渠道启动失败: %s", channel.name)

    async def stop(self) -> None:
        """Stops every member, then reports all failures together."""
        self._ctx = None
        errors: list[Exception] = []
        for channel in reversed(list(self._members.values())):
            try:
                await channel.stop()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup(f"{self.name} 账号渠道停止失败", errors)

    def pause_intake(self) -> None:
        """Pauses every member before a runtime handover."""
        self._paused = True
        for channel in self._members.values():
            channel.pause_intake()

    def resume_intake(self) -> None:
        """Resumes every member after a handover or a rejected one."""
        self._paused = False
        for channel in self._members.values():
            channel.resume_intake()
