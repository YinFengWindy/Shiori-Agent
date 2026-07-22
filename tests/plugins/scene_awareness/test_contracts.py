from typing import Any, cast

import pytest

from agent.provider import ToolCall
from plugins.scene_awareness.contracts import (
    SCENE_DECISION_TOOL_NAME,
    SceneDecisionProtocolError,
    parse_scene_decision_tool_call,
)


def _arguments(**overrides: Any) -> dict[str, Any]:
    payload = {
        "transition": "started",
        "should_generate": True,
        "scene_key": "rain-confession",
        "prompt": "1girl, standing in rain, night",
        "negative_prompt": "blurry, text",
        "size_preset": "portrait",
    }
    payload.update(overrides)
    return payload


def _call(**overrides: Any) -> ToolCall:
    return ToolCall("scene-1", SCENE_DECISION_TOOL_NAME, _arguments(**overrides))


def test_parse_tool_call_returns_validated_started_decision() -> None:
    decision = parse_scene_decision_tool_call(
        [_call()],
        current_scene_key="",
        content_length=0,
    )

    assert decision.transition == "started"
    assert decision.scene_key == "rain-confession"
    assert decision.should_generate is True


@pytest.mark.parametrize("transition", ["closed", "none"])
def test_parse_tool_call_accepts_empty_terminal_decision(transition: str) -> None:
    decision = parse_scene_decision_tool_call(
        [
            _call(
                transition=transition,
                should_generate=False,
                scene_key="",
                prompt="",
                negative_prompt="",
                size_preset="",
            )
        ],
        current_scene_key="bedroom-night" if transition == "closed" else "",
        content_length=0,
    )

    assert decision.transition == transition
    assert decision.should_generate is False
    assert decision.size_preset == ""


@pytest.mark.parametrize(
    ("tool_calls", "current_scene_key", "error"),
    [
        ([], "", "必须调用一次"),
        (
            [
                _call(),
                _call(scene_key="rain-confession-2"),
            ],
            "",
            "必须调用一次",
        ),
        ([ToolCall("scene-1", "other", _arguments())], "", "错误的提交工具"),
        (
            [
                ToolCall(
                    "scene-1",
                    SCENE_DECISION_TOOL_NAME,
                    cast(Any, ["not", "an", "object"]),
                )
            ],
            "",
            "参数必须是对象",
        ),
        (
            [
                ToolCall(
                    "scene-1",
                    SCENE_DECISION_TOOL_NAME,
                    {"transition": "started"},
                )
            ],
            "",
            "缺少参数",
        ),
        (
            [
                _call(
                    transition="changed",
                    scene_key="",
                )
            ],
            "old-scene",
            "缺少 scene_key",
        ),
        (
            [
                _call(
                    transition="none",
                    should_generate=False,
                    scene_key="empty_void",
                    prompt="",
                    negative_prompt="",
                    size_preset="",
                )
            ],
            "",
            "不能提供场景或图像参数",
        ),
        (
            [_call(should_generate=False)],
            "",
            "started 必须生成 CG",
        ),
        (
            [
                _call(
                    transition="closed",
                    should_generate=True,
                    scene_key="",
                    prompt="",
                    negative_prompt="",
                    size_preset="",
                )
            ],
            "old-scene",
            "closed 不能生成 CG",
        ),
        (
            [
                _call(
                    transition="none",
                    should_generate=False,
                    scene_key="",
                    prompt="",
                    negative_prompt="",
                    size_preset="",
                )
            ],
            "old-scene",
            "已有场景",
        ),
        (
            [_call(transition="changed", scene_key="old-scene")],
            "old-scene",
            "新的 scene_key",
        ),
        (
            [_call(prompt="雨中的少女")],
            "",
            "仅支持英文 NovelAI tags",
        ),
    ],
)
def test_parse_tool_call_rejects_invalid_protocol(
    tool_calls: list[ToolCall],
    current_scene_key: str,
    error: str,
) -> None:
    with pytest.raises(SceneDecisionProtocolError, match=error):
        parse_scene_decision_tool_call(
            tool_calls,
            current_scene_key=current_scene_key,
            content_length=17,
        )
