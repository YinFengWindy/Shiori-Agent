from __future__ import annotations

from datetime import datetime, timezone

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
    assert service.summary("mira") is None

    state = service.initialize("mira", value=45, reason="设定里是老朋友", now=_NOW)

    assert (state.value, state.stage_floor) == (45, 40)
    assert service.read_state("mira") == state
    assert service.summary("mira") == {
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
    assert service.apply_delta("mira", delta=3, reason="升", source="turn").value == 61
    after_drop = service.apply_delta("mira", delta=-5, reason="降", source="decay")
    assert (after_drop.value, after_drop.stage_floor) == (60, 60)
    # Fully absorbed by the floor: nothing changes and no entry is written.
    assert (
        service.apply_delta("mira", delta=-3, reason="再降", source="turn").value == 60
    )

    assert _history(service) == [
        ("init", None, 58, None, "初始"),
        ("turn", 58, 61, 3, "升"),
        ("decay", 61, 60, -1, "降"),
    ]
    assert service.summary("mira") == {"value": 60, "stage": "亲密", "progress": 0.0}


def test_value_is_capped_at_100_and_requires_initialization(tmp_path):
    service = RoleAffectionService(tmp_path)
    with pytest.raises(RuntimeError, match="尚未初始化"):
        service.apply_delta("mira", delta=1, reason="x", source="turn")

    service.initialize("mira", value=99, reason="初始", now=_NOW)
    assert service.apply_delta("mira", delta=3, reason="满", source="turn").value == 100
    assert (
        service.apply_delta("mira", delta=3, reason="溢出", source="turn").value == 100
    )

    assert [entry.after for entry in service.read_history("mira")] == [99, 100]
    assert service.summary("mira") == {"value": 100, "stage": "挚爱", "progress": 1.0}


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
        service.apply_delta("mira", delta=1, reason=f"第{step}轮", source="turn")

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
