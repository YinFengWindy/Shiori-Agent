"""Account member channels start, pause and stop with their group at runtime."""

from __future__ import annotations

import logging

import pytest

from infra.channels.account_group import AccountChannelGroup
from infra.channels.contract import ChannelContext


class _Member:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.events: list[object] = []

    async def start(self, ctx: ChannelContext) -> None:
        self.events.append(("start", ctx.intake_paused))
        if self.fail:
            raise ConnectionError("token rejected")

    async def stop(self) -> None:
        self.events.append("stop")

    def pause_intake(self) -> None:
        self.events.append("pause")

    def resume_intake(self) -> None:
        self.events.append("resume")


def _context() -> ChannelContext:
    return ChannelContext(
        bus=None,  # type: ignore[arg-type]
        session_manager=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
        push_tool=None,  # type: ignore[arg-type]
        attachment_store=None,  # type: ignore[arg-type]
        http_resources=None,  # type: ignore[arg-type]
        interrupt_controller=None,
        bot_commands=[],
        log=logging.getLogger("test"),
        intake_paused=True,
    )


@pytest.mark.asyncio
async def test_members_join_and_leave_a_running_group_without_a_restart():
    group = AccountChannelGroup("telegram")
    saved, broken = _Member("telegram_1"), _Member("telegram_2", fail=True)
    await group.add("1", saved)  # type: ignore[arg-type]
    await group.add("2", broken)  # type: ignore[arg-type]
    # One account failing to connect leaves the group and its others running.
    await group.start(_context())
    assert saved.events == [("start", True)]

    group.resume_intake()
    added = _Member("telegram_3")
    await group.add("3", added)  # type: ignore[arg-type]
    assert added.events == [("start", False)]
    assert await group.remove("3") is added
    assert added.events == [("start", False), "stop"]
    assert group.member_channel("telegram_3") is None

    await group.stop()
    assert saved.events[-1] == "stop"
    assert broken.events[-1] == "stop"
