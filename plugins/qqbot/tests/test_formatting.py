from __future__ import annotations

from plugins.qqbot.backend.formatting import format_turn_live


def test_live_format_keeps_latest_tail_with_marker() -> None:
    result = format_turn_live("x" * 1000)

    assert len(result) == 900
    assert result.startswith("...")
