"""An in-memory ``SCHEDULE_HOST`` for the plugin's own tests.

The host's real port (role turns, deliveries, delivery keys) is tested in
the host tree.
"""

from __future__ import annotations

import asyncio

import pytest
from shiori_sdk.core.schedule_host import ScheduledRun


class FakeScheduleHost:
    """Records deliveries and turns; ``hold`` keeps a turn running until set."""

    def __init__(self) -> None:
        self.deliveries: list[tuple[ScheduledRun, str, bool]] = []
        self.turns: list[tuple[ScheduledRun, str]] = []
        self.reply = "今天会下雨，记得带伞"
        self.hold: asyncio.Event | None = None
        self.turn_started = asyncio.Event()
        self.delivered = asyncio.Event()
        self.turn_cancelled = False

    async def deliver(
        self, run: ScheduledRun, message: str, *, already_persisted: bool = False
    ) -> str:
        self.deliveries.append((run, message, already_persisted))
        self.delivered.set()
        return "sent"

    async def run_turn(self, run: ScheduledRun, prompt: str) -> str:
        self.turns.append((run, prompt))
        self.turn_started.set()
        if self.hold is not None:
            try:
                await self.hold.wait()
            except asyncio.CancelledError:
                self.turn_cancelled = True
                raise
        return self.reply


@pytest.fixture
def host() -> FakeScheduleHost:
    return FakeScheduleHost()
