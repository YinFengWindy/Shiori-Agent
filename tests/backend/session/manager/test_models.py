from session.manager.models import Session


def _assistant(calls: list[dict[str, object]], **extra: object) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": "ok",
        "tool_chain": [{"text": "", "calls": calls}],
        **extra,
    }


def test_get_history_tool_names_collects_called_and_unlocked_tools_in_order():
    session = Session(
        key="s",
        messages=[
            {"role": "user", "content": "a"},
            _assistant(
                [
                    {"call_id": "1", "name": "tool_search", "unlocked": ["open"]},
                    {"call_id": "2", "name": "open"},
                ]
            ),
            {"role": "user", "content": "b"},
            _assistant(
                [
                    {"call_id": "3", "name": "click"},
                    {"call_id": "4", "name": "open"},
                ]
            ),
        ],
    )

    assert session.get_history_tool_names() == ["tool_search", "open", "click"]


def test_get_history_tool_names_drops_tools_consolidated_out_of_window():
    session = Session(
        key="s",
        messages=[
            {"role": "user", "content": "old"},
            _assistant([{"call_id": "1", "name": "old_tool"}]),
            {"role": "user", "content": "new"},
            _assistant([{"call_id": "2", "name": "new_tool"}]),
        ],
    )

    assert session.get_history_tool_names(start_index=2) == ["new_tool"]


def test_get_history_tool_names_skips_proactive_tool_chain():
    """主动消息的工具链不进入 LLM 历史，所以也不应让工具保持可见。"""
    session = Session(
        key="s",
        messages=[
            _assistant([{"call_id": "1", "name": "proactive_tool"}], proactive=True),
            {"role": "user", "content": "hi"},
        ],
    )

    assert session.get_history_tool_names() == []
