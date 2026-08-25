from __future__ import annotations

import asyncio
import base64
import binascii
import threading
from collections.abc import Callable, Iterable
from typing import Any

from desktop_bridge.voice.voice_assets import VoiceAssetLifecycle
from desktop_bridge.voice.voice_service import VoiceService


class DesktopVoiceHandler:
    """Owns desktop voice requests and keeps provider work off the event loop."""

    def __init__(
        self,
        *,
        workspace,
        voice_service: VoiceService,
        active_runtime_configs: Iterable[object],
        cancel_voice_turn: Callable[[str], bool],
    ) -> None:
        self.voice_service = voice_service
        self.assets = VoiceAssetLifecycle(workspace, voice_service.delete_managed_voice)
        self._cancel_voice_turn = cancel_voice_turn
        self._active_runtime_configs = tuple(active_runtime_configs)
        self._recovery_task: asyncio.Task[None] | None = None
        self._synthesis_cancel_events: dict[str, threading.Event] = {}
        self._synthesis_lock = threading.Lock()

    def start(self) -> None:
        """Starts one background orphan-recovery task in the active event loop."""

        if self._recovery_task is not None:
            return
        self._recovery_task = asyncio.create_task(
            asyncio.to_thread(
                self.assets.recover_orphans,
                self._active_runtime_configs,
            ),
            name="desktop-voice-recover-orphans",
        )

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one voice method, returning its response payload when recognized."""

        if method == "voice.turn.cancel":
            voice_turn_id = str(payload.get("voice_turn_id") or "").strip()
            if not voice_turn_id:
                raise ValueError("voice_turn_id 不能为空")
            return {
                "cancelled": self._cancel_voice_turn(voice_turn_id),
                "voice_turn_id": voice_turn_id,
            }
        if method == "voice.synthesize.cancel":
            voice_request_id = str(payload.get("voice_request_id") or "").strip()
            if not voice_request_id:
                raise ValueError("voice_request_id 不能为空")
            with self._synthesis_lock:
                cancel_event = self._synthesis_cancel_events.get(voice_request_id)
            if cancel_event is not None:
                cancel_event.set()
            return {"cancelled": cancel_event is not None, "voice_request_id": voice_request_id}
        if method == "voice.transcribe":
            audio = _decode_audio(payload)
            result = await asyncio.to_thread(
                self.voice_service.transcribe_result, audio
            )
            return {"text": result.text, "metrics": result.metrics.to_dict()}
        if method == "voice.synthesize":
            text = str(payload.get("text") or "").strip()
            voice_id = str(payload.get("voice_id") or "").strip()
            if not text or not voice_id:
                raise ValueError("text 和 voice_id 不能为空")
            speed = float(payload.get("speed", 1.0))
            emotion = str(payload.get("emotion") or "").strip()
            voice_request_id = str(payload.get("voice_request_id") or "").strip()
            if not voice_request_id:
                raise ValueError("voice_request_id 不能为空")
            cancel_event = threading.Event()
            with self._synthesis_lock:
                self._synthesis_cancel_events[voice_request_id] = cancel_event
            try:
                audio = await asyncio.to_thread(
                    self.voice_service.synthesize,
                    text,
                    voice_id=voice_id,
                    speed=speed,
                    emotion=emotion,
                    cancel_event=cancel_event,
                )
            finally:
                with self._synthesis_lock:
                    self._synthesis_cancel_events.pop(voice_request_id, None)
            return {
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "format": "mp3",
            }
        if method == "voice.clone":
            audio = _decode_audio(payload)
            file_name = str(payload.get("file_name") or "voice-clone.wav").strip()
            result = await asyncio.to_thread(
                self.voice_service.clone_voice,
                audio,
                file_name=file_name,
            )
            await asyncio.to_thread(self.assets.track_clone, result)
            return result
        if method == "voice.clone.abandon":
            provider, voice_id, ownership = _voice_asset_fields(payload)
            abandoned = await asyncio.to_thread(
                self.assets.abandon_clone,
                provider=provider,
                voice_id=voice_id,
                ownership=ownership,
            )
            return {"abandoned": abandoned}
        if method == "voice.delete":
            provider, voice_id, ownership = _voice_asset_fields(payload)
            await asyncio.to_thread(
                self.voice_service.delete_managed_voice,
                provider=provider,
                voice_id=voice_id,
                ownership=ownership,
            )
            return {"deleted": True}
        return None

    async def reconcile_role_update(
        self,
        previous_runtime: object,
        current_runtime: object,
    ) -> None:
        """Moves replaced managed voices into the asynchronous cleanup queue."""

        await asyncio.to_thread(
            self.assets.reconcile_role_update,
            previous_runtime,
            current_runtime,
        )

    async def retire_deleted_role(self, runtime_config: object) -> None:
        """Queues a deleted role's managed voice without blocking bridge requests."""

        await asyncio.to_thread(self.assets.retire_deleted_role, runtime_config)

    async def aclose(self) -> None:
        """Waits for the one-time orphan recovery task."""

        with self._synthesis_lock:
            for cancel_event in self._synthesis_cancel_events.values():
                cancel_event.set()

        if self._recovery_task is not None and not self._recovery_task.done():
            await self._recovery_task


def _decode_audio(payload: dict[str, Any]) -> bytes:
    audio_base64 = str(payload.get("audio_base64") or "")
    if not audio_base64:
        raise ValueError("audio_base64 不能为空")
    try:
        return base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_base64 无效") from exc


def _voice_asset_fields(payload: dict[str, Any]) -> tuple[str, str, str]:
    provider = str(payload.get("provider") or "").strip()
    voice_id = str(payload.get("voice_id") or "").strip()
    ownership = str(payload.get("ownership") or "").strip()
    if not provider or not voice_id or not ownership:
        raise ValueError("provider、voice_id 和 ownership 不能为空")
    return provider, voice_id, ownership
