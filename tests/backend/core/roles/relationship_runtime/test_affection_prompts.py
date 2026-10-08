from __future__ import annotations

from core.roles.relationship_runtime.affection_prompts import stage_prompts_view


def test_every_stage_has_default_guidance_from_lowest_to_highest():
    view = stage_prompts_view({})
    assert [row["stage"] for row in view] == [
        "厌恶",
        "冷淡",
        "陌生",
        "熟悉",
        "朋友",
        "亲密",
        "挚爱",
    ]
    assert all(row["default"] and not row["overridden"] for row in view)
