"""``[plugins.proactive]`` strategy switches."""

from __future__ import annotations

import pytest

from proactive_v2.preferences import load_proactive_preferences


def test_a_string_switch_is_rejected() -> None:
    with pytest.raises(
        ValueError, match="plugins.proactive.scene_followup 必须是布尔值"
    ):
        load_proactive_preferences({"proactive": {"scene_followup": "false"}})
