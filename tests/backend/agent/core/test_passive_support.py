from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
import json

from agent.core.passive_support import (
    update_session_runtime_metadata,
    estimate_history_budget,
    build_post_reply_context_budget,
)


def _make_session() -> SimpleNamespace:
    session = SimpleNamespace()
    session.metadata = {}
    return session


def test_update_session_runtime_metadata_counts_tool_calls_across_groups():
    session = _make_session()
    tool_chain = [
        {"calls": [{"name": "shell"}, {"name": "web_search"}]},
        {"calls": [{"name": "read_file"}]},
    ]

    update_session_runtime_metadata(
        session,
        tools_used=["shell", "web_search", "read_file"],
        tool_chain=tool_chain,
    )

    assert session.metadata["last_turn_tool_calls_count"] == 3


def test_update_session_runtime_metadata_sets_iso_last_turn_ts():
    session = _make_session()

    update_session_runtime_metadata(session, tools_used=[], tool_chain=[])

    ts = session.metadata.get("last_turn_ts", "")
    assert ts and "T" in ts


def test_estimate_history_budget_keeps_character_diagnostics_and_counts_chinese():
    chinese = [{"role": "user", "content": "你好" * 100}]
    latin = [{"role": "user", "content": "ab" * 100}]
    stats = estimate_history_budget(chinese)
    assert stats["messages"] == 1
    assert stats["chars"] == len(json.dumps(chinese, ensure_ascii=False))
    assert stats["tokens"] >= 400
    assert stats["tokens"] > estimate_history_budget(latin)["tokens"] * 3
    assert estimate_history_budget([]) == {"messages": 0, "chars": 0, "tokens": 0}


def test_history_image_cost_is_independent_of_base64_character_count():
    def history(url):
        return [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": url}}],
            }
        ]

    remote = estimate_history_budget(history("https://example.test/image.png"))
    inline = estimate_history_budget(history("data:image/png;base64," + "a" * 100000))
    assert inline["chars"] > remote["chars"] * 100
    assert inline["tokens"] == remote["tokens"] >= 4096


def test_build_post_reply_context_budget_combines_history_and_prompt_once():
    context = SimpleNamespace(
        last_debug_breakdown=[
            SimpleNamespace(est_tokens=100),
            SimpleNamespace(est_tokens=250),
        ]
    )
    budget = build_post_reply_context_budget(
        context=cast(Any, context),
        history=[{"role": "user", "content": "你好"}],
        history_window=40,
    )
    assert budget["history_window"] == 40
    assert budget["history_messages"] == 1
    # Two CJK characters cost four tokens; the request/message envelope adds 24.
    assert budget["history_tokens"] == 28
    assert budget["prompt_tokens"] == 350
    assert budget["next_turn_baseline_tokens"] == 378
