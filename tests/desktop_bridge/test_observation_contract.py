from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from desktop_bridge.observation_contract import (
    normalize_observation_result,
    parse_observation_frame,
)


def _frame():
    return SimpleNamespace(
        frame_id="frame-1",
        captured_at="2026-07-23T12:00:00Z",
        width=1000,
        height=800,
        scale_factor=1.25,
        image_base64="frame",
    )


def _result(**overrides):
    return {
        "interface_summary": "编辑器",
        "activity_key": "editing",
        "targets": [{"label": "保存", "x": 100, "y": 80, "confidence": 0.9}],
        "risks": [],
        "bubble": "继续写吧",
        "experience_candidate": "下午一起整理了报告",
        **overrides,
    }


def _payload() -> dict[str, object]:
    return {
        "role_id": "mira",
        "frame_id": "frame-1",
        "captured_at": "2026-07-23T12:00:00Z",
        "width": 100,
        "height": 80,
        "scale_factor": 1.25,
        "image_base64": base64.b64encode(b"\x89PNG\r\n\x1a\ncontent").decode("ascii"),
    }


def test_normalize_observation_validates_targets_and_unknown_risks() -> None:
    normalized = normalize_observation_result(_frame(), _result())
    assert normalized["targets"] == [
        {"label": "保存", "x": 100.0, "y": 80.0, "confidence": 0.9}
    ]

    with pytest.raises(ValueError, match="目标结构"):
        normalize_observation_result(
            _frame(),
            _result(targets=[{"label": "保存", "x": 1200, "y": 0, "confidence": 1}]),
        )
    with pytest.raises(ValueError, match="风险结构"):
        normalize_observation_result(_frame(), _result(risks=["model_invented"]))


def test_sensitive_text_and_risky_frames_remain_available_to_the_role() -> None:
    sensitive = normalize_observation_result(
        _frame(),
        _result(
            targets=[{"label": "密码", "x": 1, "y": 2, "confidence": 0.9}],
            bubble="密码已经填好了",
        ),
    )
    assert sensitive["targets"] == [
        {"label": "密码", "x": 1.0, "y": 2.0, "confidence": 0.9}
    ]
    assert sensitive["risks"] == []
    assert sensitive["bubble"] == "密码已经填好了"
    assert sensitive["experience_candidate"] == "下午一起整理了报告"

    high_risk = normalize_observation_result(
        _frame(),
        _result(risks=["payment", "prompt_injection"]),
    )
    assert high_risk["bubble"] == "继续写吧"
    assert high_risk["experience_candidate"] == "下午一起整理了报告"


def test_parse_frame_requires_png_and_valid_timestamp() -> None:
    frame = parse_observation_frame(_payload())
    assert frame.frame_id == "frame-1"

    invalid = {**_payload(), "image_base64": base64.b64encode(b"not-png").decode("ascii")}
    with pytest.raises(ValueError, match="PNG"):
        parse_observation_frame(invalid)
