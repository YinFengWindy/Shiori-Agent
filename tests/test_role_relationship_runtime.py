from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles import LonelinessHeartbeatLoop, RoleRelationshipRuntimeService, RoleStore
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _runtime(tmp_path: Path) -> tuple[RoleRelationshipRuntimeService, SessionManager, PresenceStore]:
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    presence = PresenceStore(session_manager._store)
    runtime = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        presence=presence,
    )
    return runtime, session_manager, presence


def _seed_role(tmp_path: Path, *, role_id: str = "mira") -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id=role_id,
        name="Mira",
        description="",
        system_prompt="you are mira",
    )


def _snapshot_payload(*, role_id: str = "mira") -> dict:
    return {
        "role_id": role_id,
        "role_self_view": "我最近会不自觉地去想你会不会来找我。",
        "relation_tags": ["亲近", "等你主动"],
        "internal_profile": {
            "relation_state": {
                "closeness": 0.75,
                "dependence": 0.62,
                "security": 0.35,
                "initiative_desire": 0.7,
                "neglect_sensitivity": 0.8,
            },
            "behavior_profile": {
                "loneliness_growth_base": 2.0,
                "loneliness_growth_when_unanswered": 3.0,
                "trigger_threshold": 60.0,
                "post_trigger_cooldown_minutes": 120,
                "night_suppression": 0.4,
            },
        },
        "source_summary": {},
        "generated_at": "2026-07-06T18:00:00+08:00",
        "last_attempted_at": "2026-07-06T18:00:00+08:00",
        "last_source_message_count": 4,
        "last_error": "",
    }


def test_snapshot_rejects_non_first_person_self_view(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, _, _ = _runtime(tmp_path)

    with pytest.raises(ValueError):
        runtime.write_snapshot(
            "mira",
            {
                **_snapshot_payload(),
                "role_self_view": "她最近越来越在意用户会不会主动。",
            },
        )


def test_user_message_clears_unanswered_state_and_reduces_loneliness(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, session_manager, presence = _runtime(tmp_path)
    runtime.write_snapshot("mira", _snapshot_payload())
    runtime.write_loneliness_runtime(
        "mira",
        {
            "role_id": "mira",
            "loneliness_value": 80,
            "last_calculated_at": "2026-07-06T10:00:00+00:00",
            "last_user_at": "",
            "last_proactive_at": "",
            "awaiting_reply_after_proactive": True,
            "awaiting_reply_since": "2026-07-06T09:00:00+00:00",
            "last_triggered_at": "",
            "cooldown_until": "",
        },
    )

    now = _utc(2026, 7, 6, 12, 0)
    presence.record_user_message(session_manager.role_session_key("mira"), now=now)
    updated = runtime.handle_user_message(session_manager.role_session_key("mira"), now=now)

    assert updated is not None
    assert updated["awaiting_reply_after_proactive"] is False
    assert updated["awaiting_reply_since"] == ""
    assert updated["loneliness_value"] < 80
    assert datetime.fromisoformat(updated["last_user_at"]).astimezone(timezone.utc) == now


def test_snapshot_growth_profile_is_raised_to_default_floor(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, _, _ = _runtime(tmp_path)
    payload = _snapshot_payload()
    payload["internal_profile"]["behavior_profile"]["loneliness_growth_base"] = 1.2
    payload["internal_profile"]["behavior_profile"]["loneliness_growth_when_unanswered"] = 1.8

    saved = runtime.write_snapshot("mira", payload)

    profile = saved["internal_profile"]["behavior_profile"]
    assert profile["loneliness_growth_base"] == 1.6
    assert profile["loneliness_growth_when_unanswered"] == 2.4


def test_current_loneliness_runtime_catches_up_elapsed_time_since_last_calculation(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, _, _ = _runtime(tmp_path)
    runtime.write_snapshot("mira", _snapshot_payload())
    runtime.write_loneliness_runtime(
        "mira",
        {
            "role_id": "mira",
            "loneliness_value": 10,
            "last_calculated_at": "2026-07-06T00:00:00+00:00",
            "last_user_at": "",
            "last_proactive_at": "",
            "awaiting_reply_after_proactive": False,
            "awaiting_reply_since": "",
            "last_triggered_at": "",
            "cooldown_until": "",
        },
    )

    updated = runtime.current_loneliness_runtime(
        "mira",
        now=_utc(2026, 7, 7, 0, 0),
    )

    assert updated is not None
    assert updated["loneliness_value"] == 58
    assert datetime.fromisoformat(updated["last_calculated_at"]).astimezone(timezone.utc) == _utc(2026, 7, 7, 0, 0)


def test_proactive_sent_marks_unanswered_and_sets_cooldown(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, session_manager, _ = _runtime(tmp_path)
    runtime.write_snapshot("mira", _snapshot_payload())

    now = _utc(2026, 7, 6, 8, 0)
    updated = runtime.handle_proactive_sent(session_manager.role_session_key("mira"), now=now)

    assert updated is not None
    assert updated["awaiting_reply_after_proactive"] is True
    assert datetime.fromisoformat(updated["awaiting_reply_since"]).astimezone(timezone.utc) == now
    assert datetime.fromisoformat(updated["last_triggered_at"]).astimezone(timezone.utc) == now
    assert datetime.fromisoformat(updated["cooldown_until"]).astimezone(timezone.utc) == now + timedelta(minutes=120)


def test_should_trigger_proactive_respects_threshold(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, session_manager, _ = _runtime(tmp_path)
    runtime.write_snapshot("mira", _snapshot_payload())
    runtime.write_loneliness_runtime(
        "mira",
        {
            "role_id": "mira",
            "loneliness_value": 70,
            "last_calculated_at": "2026-07-06T12:00:00+00:00",
            "last_user_at": "",
            "last_proactive_at": "",
            "awaiting_reply_after_proactive": False,
            "awaiting_reply_since": "",
            "last_triggered_at": "",
            "cooldown_until": "",
        },
    )

    should_trigger, meta = runtime.should_trigger_proactive(
        session_manager.role_session_key("mira"),
        now=_utc(2026, 7, 6, 12, 0),
    )

    assert should_trigger is True
    assert meta["reason"] == "threshold"


def test_loneliness_heartbeat_loop_defaults_to_three_minutes(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, _, _ = _runtime(tmp_path)

    loop = LonelinessHeartbeatLoop(
        runtime,
        role_store=RoleStore(tmp_path),
    )

    assert loop._interval == 3 * 60


@pytest.mark.asyncio
async def test_generate_snapshot_via_llm_accepts_prompt_json_example(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, session_manager, _ = _runtime(tmp_path)
    session = session_manager.get_or_create(session_manager.role_session_key("mira"))
    session.messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "我在。"},
    ]

    class _Resp:
        content = (
            '{"role_self_view":"我会留意你有没有来找我。",'
            '"relation_tags":["亲近"],'
            '"relation_state":{"closeness":0.6,"dependence":0.5,"security":0.4,"initiative_desire":0.7,"neglect_sensitivity":0.8},'
            '"behavior_profile":{"loneliness_growth_base":1.5,"loneliness_growth_when_unanswered":2.2,"trigger_threshold":60,"post_trigger_cooldown_minutes":120,"night_suppression":0.4}}'
        )

    class _Provider:
        async def chat(self, **kwargs):
            return _Resp()

    snapshot = await runtime.generate_snapshot_via_llm(
        "mira",
        provider=_Provider(),
        model="test-model",
    )

    assert snapshot["role_self_view"] == "我会留意你有没有来找我。"
    assert snapshot["relation_tags"] == ["亲近"]
    assert snapshot["last_source_message_count"] == 2


@pytest.mark.asyncio
async def test_refresh_snapshot_after_consolidation_updates_session_metadata(tmp_path: Path):
    _seed_role(tmp_path)
    runtime, session_manager, _ = _runtime(tmp_path)
    session = session_manager.get_or_create(session_manager.role_session_key("mira"))
    session.metadata["role_id"] = "mira"
    session.messages = [{"role": "user", "content": "你好"}] * 6
    expected_snapshot = {
        **_snapshot_payload(),
        "last_source_message_count": 6,
    }
    optimizer = SimpleNamespace(
        optimize=AsyncMock(return_value=expected_snapshot),
    )

    snapshot = await runtime.refresh_snapshot_after_consolidation(
        session,
        optimizer=optimizer,
    )

    assert snapshot == expected_snapshot
    optimizer.optimize.assert_awaited_once_with(role_id="mira")
    assert session.metadata["relationship_snapshot"]["last_source_message_count"] == 6
