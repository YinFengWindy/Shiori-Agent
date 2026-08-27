from __future__ import annotations

import asyncio
import threading

import pytest

from desktop_bridge.voice.voice_handler import DesktopVoiceHandler
from desktop_bridge.voice.voice_models import VoiceServiceError


@pytest.mark.asyncio
async def test_world_voice_synthesis_cancel_reaches_provider_event(tmp_path) -> None:
    started = threading.Event()
    cancelled = threading.Event()

    class FakeVoiceService:
        def delete_managed_voice(self, **_kwargs) -> None:
            return None

        def synthesize(self, _text, *, voice_id, speed, emotion, cancel_event):
            del voice_id, speed, emotion
            started.set()
            if cancel_event.wait(timeout=1):
                cancelled.set()
            raise VoiceServiceError("语音合成已取消", error_code="cancelled")

    handler = DesktopVoiceHandler(
        workspace=tmp_path,
        voice_service=FakeVoiceService(),  # type: ignore[arg-type]
        active_runtime_configs=(),
        cancel_voice_turn=lambda _turn_id: False,
    )
    request_id = "world-voice-cancel-1"
    synthesis = asyncio.create_task(
        handler.handle(
            "voice.synthesize",
            {
                "text": "正在合成。",
                "voice_id": "voice-1",
                "speed": 1.0,
                "voice_request_id": request_id,
            },
        )
    )

    assert await asyncio.to_thread(started.wait, 1)
    result = await handler.handle(
        "voice.synthesize.cancel",
        {"voice_request_id": request_id},
    )
    assert result == {"cancelled": True, "voice_request_id": request_id}
    with pytest.raises(VoiceServiceError, match="已取消"):
        await synthesis
    assert cancelled.is_set()
