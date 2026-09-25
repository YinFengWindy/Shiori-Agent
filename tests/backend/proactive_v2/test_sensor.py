from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.roles import RoleAggregateService, RoleStore
from proactive_v2.sensor import Sensor
from session.manager import SessionManager


def _role_service(tmp_path: Path) -> tuple[SessionManager, RoleAggregateService]:
    session_manager = SessionManager(tmp_path)
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = role_service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    return session_manager, role_service


def _sensor(
    session_manager: SessionManager,
    role_service: RoleAggregateService,
    *,
    channel: str,
    chat_id: str,
) -> Sensor:
    return Sensor(
        cfg=SimpleNamespace(
            default_role_id="mira",
            default_channel=channel,
            default_chat_id=chat_id,
            recent_chat_messages=5,
        ),
        sessions=session_manager,
        state=SimpleNamespace(),
        memory=None,
        presence=None,
        rng=None,
        role_bindings=role_service.bindings,
    )


def test_sensor_prefers_role_session_key_and_bound_transport(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "telegram", "42", "mira", chat_type="private", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="telegram", chat_id="42")

    assert sensor.target_session_key() == "role:mira"
    assert sensor.target_transport() == ("telegram", "42")


def test_sensor_prefers_configured_transport_when_multiple_bindings(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "telegram", "42", "mira", chat_type="private", contact_id="owner"
    )
    _ = role_service.bindings.bind(
        "qq", "gqq:7", "mira", chat_type="group", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="qq", chat_id="gqq:7")

    assert sensor.target_transport() == ("qq", "gqq:7")
    assert sensor.target_transports() == [("qq", "gqq:7"), ("telegram", "42")]


def test_sensor_requires_bound_transport(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)

    sensor = _sensor(session_manager, role_service, channel="telegram", chat_id="42")

    with pytest.raises(KeyError, match="default_role_id 未绑定 transport: mira"):
        _ = sensor.target_transport()


def test_sensor_rejects_configured_transport_not_bound_to_role(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "telegram", "42", "mira", chat_type="private", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="qq", chat_id="gqq:7")

    with pytest.raises(
        KeyError,
        match="default_role_id 配置的 target 未绑定到该角色: mira -> qq:gqq:7",
    ):
        _ = sensor.target_transport()


def test_sensor_requires_explicit_target_when_multiple_bindings(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "telegram", "42", "mira", chat_type="private", contact_id="owner"
    )
    _ = role_service.bindings.bind(
        "qq", "gqq:7", "mira", chat_type="group", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="", chat_id="")

    with pytest.raises(
        RuntimeError,
        match=(
            "default_role_id 存在多个 transport 绑定，"
            "必须显式配置 target.channel/chat_id: mira"
        ),
    ):
        _ = sensor.target_transport()


def test_sensor_supports_desktop_target_without_binding(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)

    sensor = _sensor(session_manager, role_service, channel="desktop", chat_id="")

    assert sensor.target_transport() == ("desktop", "role:mira")


def test_sensor_explains_bare_qq_group_number_in_configured_target(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "qq", "gqq:7", "mira", chat_type="group", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="qq", chat_id="7")

    # A bare number is a private chat; config must name the group as gqq:.
    with pytest.raises(KeyError, match="QQ 群请写成 gqq:7"):
        _ = sensor.target_transports()


def test_sensor_omits_qq_group_hint_when_no_matching_group_is_bound(tmp_path: Path):
    session_manager, role_service = _role_service(tmp_path)
    _ = role_service.bindings.bind(
        "qq", "gqq:8", "mira", chat_type="group", contact_id="owner"
    )

    sensor = _sensor(session_manager, role_service, channel="qq", chat_id="7")

    with pytest.raises(KeyError) as exc_info:
        _ = sensor.target_transports()
    assert "gqq:" not in str(exc_info.value)
