from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from desktop_bridge.observation_model import ObservationModelAdapter


def _adapter(provider=None) -> ObservationModelAdapter:
    return ObservationModelAdapter(
        role_store=SimpleNamespace(
            get_required=lambda _role_id: SimpleNamespace(
                name="Mira",
                description="陪伴者",
                system_prompt="用中文回复",
            )
        ),
        provider=provider or SimpleNamespace(),
        model="vision-model",
    )


def _payload() -> dict[str, object]:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\ncontent").decode("ascii")
    return {
        "role_id": "mira",
        "frame_id": "frame-1",
        "captured_at": "2026-07-23T12:00:00Z",
        "width": 100,
        "height": 80,
        "scale_factor": 1.25,
        "image_base64": png,
        "previous_observation": {
            "activity_key": "research",
            "interface_summary": "浏览资料",
        },
        "recent_bubbles": ["这个问题快解决了"],
    }


@pytest.mark.asyncio
async def test_analyze_uses_bounded_context_and_disables_payload_snapshots() -> None:
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"interface_summary":"编辑器","activity_key":"writing",'
                    '"targets":[],"risks":[],"bubble":"继续加油",'
                    '"experience_candidate":"一起整理报告"}'
                ),
                tool_calls=[],
            )
        )
    )
    adapter = _adapter(provider)

    result = await adapter.analyze(_payload())

    assert result["activity_key"] == "writing"
    call = provider.chat.await_args.kwargs
    user_text = call["messages"][1]["content"][0]["text"]
    assert "上一帧活动=research" in user_text
    assert "近期已说过=这个问题快解决了" in user_text
    assert call["tools"][0]["function"]["name"] == "screenshot"
    assert call["payload_snapshot_enabled"] is False


@pytest.mark.asyncio
async def test_analyze_allows_only_the_screenshot_model_action() -> None:
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content="",
                tool_calls=[SimpleNamespace(name="screenshot", arguments={})],
            )
        )
    )
    adapter = _adapter(provider)

    assert await adapter.analyze(_payload()) == {"request": "screenshot"}

    provider.chat.return_value = SimpleNamespace(
        content="",
        tool_calls=[SimpleNamespace(name="click", arguments={"x": 1, "y": 2})],
    )
    with pytest.raises(ValueError, match="未授权桌面动作"):
        await adapter.analyze(_payload())

    provider.chat.return_value = SimpleNamespace(
        content='{"action":{"type":"click"}}',
        tool_calls=[],
    )
    with pytest.raises(ValueError, match="未授权桌面动作"):
        await adapter.analyze(_payload())
