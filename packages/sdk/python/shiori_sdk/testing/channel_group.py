"""In-memory account group fixture, with no host generation or failure policy."""

from dataclasses import replace
from shiori_sdk.channels import Channel, ChannelContext


class FakeAccountChannelGroup:
    """Record members and explicitly drive their lifecycle in plugin tests."""

    def __init__(self, name: str):
        self.name = name
        self.members: dict[str, Channel] = {}
        self.context: ChannelContext | None = None

    def member(self, key: str) -> Channel | None:
        """Read one contributed member."""
        return self.members.get(key)

    def member_channel(self, name: str) -> Channel | None:
        """Find a member by its transport name."""
        return next(
            (value for value in self.members.values() if value.name == name), None
        )

    def member_channels(self) -> list[Channel]:
        """Snapshot fixture members."""
        return list(self.members.values())

    async def add(self, key: str, channel: Channel) -> None:
        """Record one member, starting it only when the fixture has a runtime."""
        if key in self.members:
            raise ValueError(f"Duplicate account channel: {key}")
        self.members[key] = channel
        if self.context is not None:
            await channel.start(self.context)

    async def remove(self, key: str) -> Channel | None:
        """Remove a member and stop an explicitly started connection."""
        channel = self.members.pop(key, None)
        if channel is not None and self.context is not None:
            await channel.stop()
        return channel

    async def start(self, ctx: ChannelContext) -> None:
        """Start fixture members under the supplied public services."""
        self.context = ctx
        for channel in self.members.values():
            await channel.start(ctx)

    async def stop(self) -> None:
        """Stop each fixture member in reverse order."""
        self.context = None
        for channel in reversed(tuple(self.members.values())):
            await channel.stop()

    def pause_intake(self) -> None:
        """Keep future members on the selected intake state."""
        if self.context is not None:
            self.context = replace(self.context, intake_paused=True)
        for channel in self.members.values():
            channel.pause_intake()

    def resume_intake(self) -> None:
        """Resume existing and subsequent fixture members."""
        if self.context is not None:
            self.context = replace(self.context, intake_paused=False)
        for channel in self.members.values():
            channel.resume_intake()
