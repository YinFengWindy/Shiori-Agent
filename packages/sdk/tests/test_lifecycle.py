"""Lifecycle contract values pinned for plugins and the host alike."""

import pytest

from shiori_sdk.lifecycle import PHASE_SLOTS, require_phase_slot


def test_phase_slots_are_the_seven_host_phases_in_wiring_order() -> None:
    assert PHASE_SLOTS == (
        "before_turn",
        "before_reasoning",
        "prompt_render",
        "before_step",
        "after_step",
        "after_reasoning",
        "after_turn",
    )


def test_require_phase_slot_rejects_names_outside_the_contract() -> None:
    for slot in PHASE_SLOTS:
        require_phase_slot(slot)
    with pytest.raises(ValueError, match="未知 phase 槽位: after_everything"):
        require_phase_slot("after_everything")
