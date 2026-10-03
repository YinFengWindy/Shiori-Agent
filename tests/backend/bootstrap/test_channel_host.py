import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bootstrap.channel_host import ChannelHost


def connection(name):
    return SimpleNamespace(name=name, pause_intake=Mock(), resume_intake=Mock())


@pytest.mark.asyncio
async def test_stop_all_attempts_each_channel_once_and_reports_failure():
    host = ChannelHost(lambda channel: None)
    first, second = connection("one"), connection("two")
    first.stop = AsyncMock()
    second.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
    host.add(first)
    host.add(second)
    with pytest.raises(ExceptionGroup, match="Channel cleanup failed"):
        await host.stop_all()
    first.stop.assert_awaited_once()
    second.stop.assert_awaited_once()
    with pytest.raises(ExceptionGroup, match="Channel cleanup failed"):
        await host.stop_all()
    first.stop.assert_awaited_once()
    second.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_all_reports_prior_retirement_failure_without_retrying_stop():
    context = SimpleNamespace(push_tool=SimpleNamespace(retire_channel=Mock()))
    host = ChannelHost(lambda channel: context)
    channel = connection("one")
    channel.stop = AsyncMock(side_effect=RuntimeError("retirement failed"))
    host.add(channel)
    candidate = ChannelHost(lambda channel: context)
    await host.handover(candidate, retire_after=AsyncMock())
    await host._retirements.drain()
    with pytest.raises(ExceptionGroup, match="Channel cleanup failed"):
        await host.stop_all()
    channel.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_stop_waiter_does_not_cancel_retirement_or_lose_completion():
    context = SimpleNamespace(push_tool=SimpleNamespace(retire_channel=Mock()))
    host = ChannelHost(lambda channel: context)
    channel = connection("one")
    channel.stop = AsyncMock()
    host.add(channel)
    candidate = ChannelHost(lambda channel: context)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def ready():
        entered.set()
        await finish.wait()

    complete = AsyncMock()
    await host.handover(candidate, retire_after=ready, retire_complete=complete)
    await entered.wait()
    stopping = asyncio.create_task(host.stop_all())
    await asyncio.sleep(0)
    stopping.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stopping
    finish.set()
    await asyncio.wait_for(host.stop_all(), 1)
    channel.stop.assert_awaited_once()
    complete.assert_awaited_once()


def test_same_name_new_credentials_require_exclusive_handover():
    active = ChannelHost(lambda channel: None)
    candidate = ChannelHost(lambda channel: None)
    active.add(connection("telegram"), configuration="credential-A")
    candidate.add(connection("telegram"), configuration="credential-B")
    assert active.requires_exclusive_handover(candidate)


def test_unchanged_connection_does_not_require_draining_active_turns():
    active = ChannelHost(lambda channel: None)
    candidate = ChannelHost(lambda channel: None)
    channel = connection("telegram")
    active.add(channel)
    candidate.add(channel)
    assert not active.requires_exclusive_handover(candidate)


def test_reintroduced_name_must_drain_retained_old_credentials():
    active = ChannelHost(lambda channel: None)
    candidate = ChannelHost(lambda channel: None)
    active._retired_transports["telegram"] = connection("telegram")
    candidate.add(connection("telegram"))
    assert active.requires_exclusive_handover(candidate)


def test_pause_intake_restores_prior_channels_when_a_later_channel_fails():
    active = ChannelHost(lambda channel: None)
    first = connection("telegram")
    second = connection("qq")
    second.pause_intake.side_effect = RuntimeError("cannot pause")
    active.add(first)
    active.add(second)
    with pytest.raises(RuntimeError, match="cannot pause"):
        active.pause_intake()
    first.resume_intake.assert_called_once()


def test_resume_intake_uses_current_connections_after_publication():
    active = ChannelHost(lambda channel: None)
    old = connection("telegram")
    new = connection("telegram")
    active.add(old)
    active.pause_intake()
    active._channels = [new]
    active.resume_intake()
    old.pause_intake.assert_called_once()
    new.resume_intake.assert_called_once()
    old.resume_intake.assert_not_called()


def test_get_prefers_the_published_connection_over_a_draining_one():
    host = ChannelHost(lambda channel: None)
    published = connection("telegram")
    draining = connection("qq")
    host.add(published)
    host._retired_transports["telegram"] = connection("telegram")
    host._retired_transports["qq"] = draining

    assert host.get("telegram") is published
    assert host.get("qq") is draining
    assert host.get("qqbot") is None


class _StatusChannel:
    def __init__(self, name, status):
        self.name = name
        self._status = status

    def status(self):
        if isinstance(self._status, Exception):
            raise self._status
        return self._status


def test_snapshot_reports_registered_and_failed_channels():
    host = ChannelHost(lambda channel: None)
    host.add(connection("telegram"))
    host.add(connection("qq"))
    host.record_failure("qq", phase="start", error=ConnectionError("refused"))
    host.record_failure("broken", phase="construct", error=ValueError("bad token"))
    assert host.snapshot() == {
        "telegram": {"state": "active", "error": ""},
        "qq": {"state": "failed", "error": "start: ConnectionError: refused"},
        "broken": {"state": "failed", "error": "construct: ValueError: bad token"},
    }


def test_snapshot_passes_optional_channel_status_through():
    host = ChannelHost(lambda channel: None)
    host.add(_StatusChannel("demo", {"connected": True, "account": "@shiori_bot"}))
    assert host.snapshot()["demo"] == {
        "state": "active",
        "error": "",
        "status": {"connected": True, "account": "@shiori_bot"},
    }


def test_snapshot_reports_a_raising_status_as_failure():
    host = ChannelHost(lambda channel: None)
    host.add(_StatusChannel("demo", RuntimeError("socket gone")))
    assert host.snapshot()["demo"] == {
        "state": "failed",
        "error": "status: RuntimeError: socket gone",
    }


@pytest.mark.asyncio
async def test_account_member_channels_are_found_and_listed_through_their_group():
    from infra.channels.account_group import AccountChannelGroup

    host = ChannelHost(lambda channel: None)
    group = AccountChannelGroup("telegram")
    host.add(group)
    member = _StatusChannel("telegram_42", {"connected": True})
    await group.add("42", member)  # type: ignore[arg-type]

    assert host.get("telegram_42") is member
    assert host.get("telegram") is group
    assert host.snapshot()["telegram_42"] == {
        "state": "active",
        "error": "",
        "status": {"connected": True},
    }
