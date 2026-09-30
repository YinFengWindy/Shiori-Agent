"""A group's listening switch and cap: logged changes and the checked cap."""

from __future__ import annotations

from pathlib import Path

import pytest

from conversation.listening_switches import DEFAULT_DAILY_CAP, ListeningSwitches
from conversation.store import ConversationStore

_GROUP = "thread:mira:qq:gqq:5"


def _switches(tmp_path: Path) -> ListeningSwitches:
    return ConversationStore(tmp_path / "sessions.db").listening.switches


def test_every_switch_change_is_logged_with_its_operator(tmp_path: Path) -> None:
    switches = _switches(tmp_path)

    switches.set_enabled(_GROUP, True, operator="user")
    switches.set_enabled(_GROUP, True, operator="role")
    switches.set_enabled(_GROUP, False, operator="role")

    assert [(item.enabled, item.operator) for item in switches.toggles(_GROUP)] == [
        (False, "role"),
        (True, "user"),
    ]


def test_a_group_follows_the_default_cap_until_it_overrides_it(tmp_path: Path) -> None:
    switches = _switches(tmp_path)
    assert switches.daily_cap(_GROUP) == DEFAULT_DAILY_CAP

    switches.set_default_daily_cap(5)
    assert switches.daily_cap(_GROUP) == 5
    switches.set_daily_cap(_GROUP, 2)
    assert switches.daily_cap(_GROUP) == 2
    assert switches.set_daily_cap(_GROUP, None).daily_cap is None
    assert switches.daily_cap(_GROUP) == 5
    for bad in (0, True, "3"):
        with pytest.raises(ValueError):
            switches.set_daily_cap(_GROUP, bad)
        with pytest.raises(ValueError):
            switches.set_default_daily_cap(bad)
