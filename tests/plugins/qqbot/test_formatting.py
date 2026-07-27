from __future__ import annotations

from plugins.qqbot.formatting import format_turn_live, iter_stream_chunks


def test_stream_chunks_are_cumulative_replacements() -> None:
    assert iter_stream_chunks("abcdef", limit=2) == ["ab", "abcd", "abcdef"]


def test_live_format_keeps_latest_tail_with_marker() -> None:
    result = format_turn_live("x" * 1000)

    assert len(result) == 900
    assert result.startswith("...")
