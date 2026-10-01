from copy import deepcopy

import pytest

from agent.prompting.assembler import build_context_frame_content, PromptSectionRender
from agent.prompting.usage_anchor import UsageAnchors, input_cost, usage_context


def request(frame="time=1"):
    return {
        "model": "model-a",
        "_connection": "connection-a",
        "messages": [
            {"role": "system", "content": "固定约束"},
            {
                "role": "user",
                "content": build_context_frame_content(
                    [PromptSectionRender("time", frame, False)]
                ),
            },
            {"role": "user", "content": "你好"},
        ],
        "tools": [
            {"type": "function", "function": {"name": "read", "description": "读取"}}
        ],
    }


def test_append_and_known_dynamic_frame_delta_preserve_actual_anchor():
    tracker = UsageAnchors()
    previous = request()
    with usage_context(("role:a", "user", "", ("desktop",))):
        tracker.finish(tracker.begin(previous), 900)
        assert tracker.estimate(previous).source == "actual"
        current = request("time=222222222222; 检索新增文本")
        current["messages"] += [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "下一步"},
        ]
        estimate = tracker.estimate(current)
        assert estimate.source == "anchor_delta"
        assert estimate.tokens == 900 + input_cost(current) - input_cost(previous)


@pytest.mark.parametrize(
    "change", ["model", "connection", "history", "system", "tools", "compressed"]
)
def test_unverifiable_request_changes_invalidate_anchor(change):
    tracker = UsageAnchors()
    previous = request()
    current = deepcopy(previous)
    if change == "model":
        current["model"] = "model-b"
    elif change == "connection":
        current["_connection"] = "connection-b"
    elif change == "history":
        current["messages"][-1]["content"] = "重写"
    elif change == "system":
        current["messages"][0]["content"] += "新约束"
    elif change == "tools":
        current["tools"][0]["function"]["description"] += "新说明"
    else:
        current["messages"] = current["messages"][:1]
    with usage_context(("role:a", "user", "", ("desktop",))):
        tracker.finish(tracker.begin(previous), 900)
        assert tracker.estimate(current).source == "local"
        assert (
            tracker.estimate(previous).source == "local"
        ), "switching back must not resurrect a stale anchor"


def test_context_isolation_binding_changes_and_late_responses():
    tracker = UsageAnchors()
    payload = request()
    with usage_context(("role:a", "external", "group-a", ("desktop",))):
        old = tracker.begin(payload)
        latest = tracker.begin(payload)
        tracker.finish(latest, 120)
        tracker.finish(old, 999)
        assert tracker.estimate(payload).tokens == 120
    with usage_context(("role:a", "external", "group-b", ("desktop",))):
        assert tracker.estimate(payload).source == "local"
    with usage_context(("role:a", "external", "group-a", ("desktop", "new-bound-dm"))):
        assert tracker.estimate(payload).source == "local"
    with usage_context(("role:a", "external", "group-a", ("desktop",))):
        assert tracker.estimate(payload).source == "local"


def test_missing_usage_does_not_create_a_zero_anchor_and_snapshot_is_immutable():
    tracker = UsageAnchors()
    payload = request()
    with usage_context(("session",)):
        tracker.finish(tracker.begin(payload), None)
        assert tracker.estimate(payload).source == "local"
        ticket = tracker.begin(payload)
        payload["messages"].append({"role": "assistant", "content": "new"})
        tracker.finish(ticket, 50)
        estimate = tracker.estimate(payload)
        assert estimate.source == "anchor_delta"
        assert estimate.tokens > 50
