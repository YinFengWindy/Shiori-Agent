from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.roles.relationship_runtime import RoleAffectionService

_NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _history(service: RoleAffectionService):
    return [
        (entry.source, entry.before, entry.after, entry.delta, entry.reason)
        for entry in service.read_history("mira")
    ]


def test_initialize_sets_stage_floor_and_writes_one_init_entry(tmp_path):
    service = RoleAffectionService(tmp_path)
    assert service.read_state("mira") is None
    assert service.current_summary("mira", now=_NOW) is None

    state = service.initialize("mira", value=45, reason="设定里是老朋友", now=_NOW)

    assert (state.value, state.stage_floor) == (45, 40)
    assert service.read_state("mira") == state
    assert service.current_summary("mira", now=_NOW) == {
        "value": 45,
        "stage": "朋友",
        "progress": pytest.approx(5 / 19),
    }
    assert _history(service) == [("init", None, 45, None, "设定里是老朋友")]
    with pytest.raises(RuntimeError, match="已初始化"):
        service.initialize("mira", value=10, reason="重复", now=_NOW)
    assert len(service.read_history("mira")) == 1


def test_deductions_stop_at_the_floor_of_the_highest_stage_reached(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=58, reason="初始", now=_NOW)

    # Crossing into 亲密 raises the floor to 60; a later deduction cannot leave it.
    assert (
        service.apply_delta("mira", delta=3, reason="升", source="turn", now=_NOW).value
        == 61
    )
    after_drop = service.apply_delta(
        "mira", delta=-5, reason="降", source="decay", now=_NOW
    )
    assert (after_drop.value, after_drop.stage_floor) == (60, 60)
    # Fully absorbed by the floor: nothing changes and no entry is written.
    assert (
        service.apply_delta(
            "mira", delta=-3, reason="再降", source="turn", now=_NOW
        ).value
        == 60
    )

    assert _history(service) == [
        ("init", None, 58, None, "初始"),
        ("turn", 58, 61, 3, "升"),
        ("decay", 61, 60, -1, "降"),
    ]
    assert service.current_summary("mira", now=_NOW) == {
        "value": 60,
        "stage": "亲密",
        "progress": 0.0,
    }


def test_value_is_capped_at_100_and_requires_initialization(tmp_path):
    service = RoleAffectionService(tmp_path)
    with pytest.raises(RuntimeError, match="尚未初始化"):
        service.apply_delta("mira", delta=1, reason="x", source="turn", now=_NOW)

    service.initialize("mira", value=99, reason="初始", now=_NOW)
    assert (
        service.apply_delta("mira", delta=3, reason="满", source="turn", now=_NOW).value
        == 100
    )
    assert (
        service.apply_delta(
            "mira", delta=3, reason="溢出", source="turn", now=_NOW
        ).value
        == 100
    )

    assert [entry.after for entry in service.read_history("mira")] == [99, 100]
    assert service.current_summary("mira", now=_NOW) == {
        "value": 100,
        "stage": "挚爱",
        "progress": 1.0,
    }


def test_initial_value_outside_range_is_rejected(tmp_path):
    service = RoleAffectionService(tmp_path)
    with pytest.raises(ValueError, match="超出范围"):
        service.initialize("mira", value=101, reason="越界", now=_NOW)
    assert service.read_state("mira") is None
    assert service.read_history("mira") == []


@pytest.mark.parametrize(
    "line",
    [
        '{"time": "t", "before": 1, "after": 2, "delta": 1, "reason": "r", "source": "gift"}',
        '{"time": "t", "before": 1, "after": "2", "delta": 1, "reason": "r", "source": "turn"}',
        '{"time": "t", "after": 2, "delta": 1, "reason": "r", "source": "turn"}',
        "[1, 2]",
    ],
)
def test_history_rejects_malformed_entries(tmp_path, line):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=10, reason="初始", now=_NOW)
    with service.history_path("mira").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    with pytest.raises(ValueError):
        service.read_history("mira")


def test_history_pages_run_newest_first_and_end_at_the_init_entry(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=30, reason="初始", now=_NOW)
    for step in range(1, 5):
        service.apply_delta(
            "mira", delta=1, reason=f"第{step}轮", source="turn", now=_NOW
        )

    pages = [service.history_page("mira", page=page, page_size=2) for page in (1, 2, 3)]

    # Each entry keeps its 0-based append position as a stable id.
    assert [[(id_, entry.reason) for id_, entry in items] for items, _ in pages] == [
        [(4, "第4轮"), (3, "第3轮")],
        [(2, "第2轮"), (1, "第1轮")],
        [(0, "初始")],
    ]
    assert {total for _, total in pages} == {5}
    assert service.history_page("mira", page=4, page_size=2) == ([], 5)
    assert service.history_page("nobody", page=1, page_size=2) == ([], 0)


def _decay_entries(service: RoleAffectionService):
    return [
        (entry.time, entry.before, entry.after, entry.delta, entry.reason)
        for entry in service.read_history("mira")
        if entry.source == "decay"
    ]


def _at(delta: timedelta) -> str:
    return (_NOW + delta).astimezone().isoformat()


def test_decay_starts_three_days_after_the_last_user_message(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=45, reason="初始", now=_NOW)

    service.settle_decay("mira", now=_NOW + timedelta(days=3, seconds=-1))
    assert service.read_state("mira").value == 45
    assert _decay_entries(service) == []

    # One step per full overdue day, each dated at its own due time.
    service.settle_decay("mira", now=_NOW + timedelta(days=4, hours=23))
    assert service.read_state("mira").value == 43
    assert _decay_entries(service) == [
        (_at(timedelta(days=3)), 45, 44, -1, "长时间没有联系"),
        (_at(timedelta(days=4)), 44, 43, -1, "长时间没有联系"),
    ]


def test_backfilled_decay_equals_settling_day_by_day_and_stops_at_the_floor(
    tmp_path,
):
    end = _NOW + timedelta(days=9, hours=5)
    at_once = RoleAffectionService(tmp_path / "once")
    stepwise = RoleAffectionService(tmp_path / "stepwise")
    for service in (at_once, stepwise):
        service.initialize("mira", value=43, reason="初始", now=_NOW)

    at_once.settle_decay("mira", now=end)
    moment = _NOW
    while moment <= end:
        stepwise.settle_decay("mira", now=moment)
        moment += timedelta(hours=6)

    assert at_once.read_state("mira") == stepwise.read_state("mira")
    assert at_once.read_history("mira") == stepwise.read_history("mira")
    # 43 -> 40 on days 3–5; the 朋友 floor absorbs days 6–9 without entries.
    assert at_once.read_state("mira").value == 40
    assert [entry[2] for entry in _decay_entries(at_once)] == [42, 41, 40]


def test_a_user_message_settles_overdue_decay_then_restarts_the_timer(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=45, reason="初始", now=_NOW)

    service.record_user_activity("mira", now=_NOW + timedelta(days=3, hours=1))
    service.settle_decay("mira", now=_NOW + timedelta(days=6))

    assert service.read_state("mira").value == 44
    assert _decay_entries(service) == [
        (_at(timedelta(days=3)), 45, 44, -1, "长时间没有联系")
    ]
    service.settle_decay("mira", now=_NOW + timedelta(days=6, hours=1))
    assert service.read_state("mira").value == 43


def test_a_turn_change_settles_overdue_decay_first(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.initialize("mira", value=45, reason="初始", now=_NOW)

    turn_at = _NOW + timedelta(days=4, hours=1)
    state = service.apply_delta(
        "mira", delta=2, reason="终于来了", source="turn", now=turn_at
    )

    history = service.read_history("mira")
    assert [(entry.source, entry.after) for entry in history] == [
        ("init", 45),
        ("decay", 44),
        ("decay", 43),
        ("turn", 45),
    ]
    times = [datetime.fromisoformat(entry.time) for entry in history]
    assert times == sorted(times)
    assert datetime.fromisoformat(state.updated_at) == turn_at


@pytest.mark.parametrize(
    "timer_field",
    [
        {"last_user_message_at": _NOW.isoformat()},
        {"decay_settled_at": None},
    ],
)
def test_state_with_only_one_decay_timer_field_is_rejected(tmp_path, timer_field):
    service = RoleAffectionService(tmp_path)
    service.state_path("mira").parent.mkdir(parents=True)
    payload = {
        "role_id": "mira",
        "value": 45,
        "stage_floor": 40,
        "initialized_at": _NOW.isoformat(),
        "updated_at": _NOW.isoformat(),
    }
    service.state_path("mira").write_text(
        json.dumps(payload | timer_field), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="衰减计时字段不完整"):
        service.read_state("mira")


def test_state_saved_before_decay_tracking_counts_from_its_last_change(tmp_path):
    service = RoleAffectionService(tmp_path)
    service.state_path("mira").parent.mkdir(parents=True)
    service.state_path("mira").write_text(
        json.dumps(
            {
                "role_id": "mira",
                "value": 45,
                "stage_floor": 40,
                "initialized_at": _at(timedelta(0)),
                "updated_at": _at(timedelta(days=1)),
            }
        ),
        encoding="utf-8",
    )

    service.settle_decay("mira", now=_NOW + timedelta(days=3, hours=12))
    assert service.read_state("mira").value == 45
    service.settle_decay("mira", now=_NOW + timedelta(days=4))
    assert service.read_state("mira").value == 44
