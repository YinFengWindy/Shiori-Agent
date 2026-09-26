from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.desktop_presence import DesktopPresence
from core.roles import RoleStore
from proactive_v2.sensor import Sensor
from proactive_v2.target_selection import ProactiveTargetResolver
from session.manager import SessionManager


def _sensor(
    tmp_path: Path, presence: DesktopPresence, *, resolver: bool = True
) -> tuple[Sensor, RoleStore]:
    session_manager = SessionManager(tmp_path)
    roles = RoleStore(tmp_path)
    _ = roles.create_role(
        role_id="mira", name="Mira", description="", system_prompt="you are mira"
    )
    sensor = Sensor(
        cfg=SimpleNamespace(role_id="mira", recent_chat_messages=5),
        sessions=session_manager,
        state=SimpleNamespace(),
        memory=None,
        presence=None,
        rng=None,
        target_resolver=(
            ProactiveTargetResolver(
                roles=roles,
                conversations=session_manager.conversation_store,
                desktop_presence=presence,
            )
            if resolver
            else None
        ),
    )
    return sensor, roles


def _save_candidates(roles: RoleStore, *candidates: dict[str, str]) -> None:
    _ = roles.update_role(
        "mira",
        channel_bindings=[
            {"channel": "desktop", "chat_id": "role:mira", "chat_type": "private"},
            {"channel": "telegram", "chat_id": "42", "chat_type": "private"},
        ],
        proactive={"enabled": bool(candidates), "candidates": list(candidates)},
    )


def test_sensor_selects_among_the_saved_candidates_at_call_time(tmp_path: Path):
    presence = DesktopPresence()
    sensor, roles = _sensor(tmp_path, presence)
    _save_candidates(
        roles,
        {"channel": "desktop", "chat_id": "role:mira"},
        {"channel": "telegram", "chat_id": "42"},
    )

    assert sensor.target_session_key() == "role:mira"
    assert sensor.target_transport() == ("desktop", "role:mira")
    presence.report(False)
    assert sensor.target_transport() == ("desktop", "role:mira")
    # Candidate edits apply to the next selection without rebuilding the loop.
    _save_candidates(roles, {"channel": "desktop", "chat_id": "role:mira"})
    assert sensor.target_transport() == ("desktop", "role:mira")


def test_sensor_has_no_target_without_candidates(tmp_path: Path):
    sensor, roles = _sensor(tmp_path, DesktopPresence())
    _save_candidates(roles)

    assert sensor.target_transport() is None


def test_sensor_refuses_to_pick_a_target_without_a_resolver(tmp_path: Path):
    sensor, _ = _sensor(tmp_path, DesktopPresence(), resolver=False)

    with pytest.raises(RuntimeError, match="目标选择服务"):
        _ = sensor.target_transport()
