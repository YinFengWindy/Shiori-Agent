from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bootstrap.channel_host import ChannelHost


def connection(name):
    return SimpleNamespace(name=name, pause_intake=Mock(), resume_intake=Mock())


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
