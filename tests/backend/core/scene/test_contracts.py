from dataclasses import fields

import pytest

from agent.provider import ToolCall
from shiori_sdk.role_events import SceneObservationCommitted
from core.scene.contracts import (
    SCENE_DECISION_TOOL_NAME,
    SceneDecision,
    SceneDecisionProtocolError,
    parse_scene_decision_tool_call,
)


def _call(**overrides):
    payload = dict(
        transition="started",
        scene_key="rain",
        visual_key="rain-standing",
        visual_description="少女撑伞站在雨夜车站，灯光照亮她的粉色头发。",
    )
    payload.update(overrides)
    return ToolCall("scene", SCENE_DECISION_TOOL_NAME, payload)


def test_neutral_facts_accept_natural_language_and_exclude_provider_contracts():
    decision = parse_scene_decision_tool_call(
        [_call()], current_scene_key="", content_length=0
    )
    assert decision.visual_description.startswith("少女撑伞")
    for contract in (SceneDecision, SceneObservationCommitted):
        assert not {"should_generate", "prompt", "negative_prompt", "size_preset"} & {
            field.name for field in fields(contract)
        }


@pytest.mark.parametrize("transition", ["closed", "none"])
def test_terminal_scene_carries_no_visual_facts(transition):
    decision = parse_scene_decision_tool_call(
        [
            _call(
                transition=transition,
                scene_key="",
                visual_key="",
                visual_description="",
            )
        ],
        current_scene_key="rain" if transition == "closed" else "",
        content_length=0,
    )
    assert decision.transition == transition
    assert not decision.visual_description


@pytest.mark.parametrize(
    "calls,current,error",
    [
        ([], "", "必须调用一次"),
        ([_call(), _call()], "", "必须调用一次"),
        ([ToolCall("scene", "other", {})], "", "错误的提交工具"),
        ([ToolCall("scene", SCENE_DECISION_TOOL_NAME, {})], "", "缺少参数"),
        ([_call(transition="changed", scene_key="rain")], "rain", "新的 scene_key"),
        (
            [_call(transition="same", scene_key="other")],
            "rain",
            "沿用 current_scene_key",
        ),
        ([_call(visual_description="")], "", "缺少 visual_description"),
        (
            [
                _call(
                    transition="none",
                    scene_key="",
                    visual_key="",
                    visual_description="",
                )
            ],
            "rain",
            "已有场景",
        ),
        ([_call(prompt="1girl")], "", "未知参数"),
    ],
)
def test_invalid_protocol_fails(calls, current, error):
    with pytest.raises(SceneDecisionProtocolError, match=error):
        parse_scene_decision_tool_call(
            calls, current_scene_key=current, content_length=17
        )


def test_same_scene_allows_both_unchanged_and_changed_visual_facts():
    for visual in ("standing", "sitting"):
        decision = parse_scene_decision_tool_call(
            [_call(transition="same", visual_key=visual)],
            current_scene_key="rain",
            current_visual_key="standing",
            content_length=0,
        )
        assert decision.visual_key == visual
