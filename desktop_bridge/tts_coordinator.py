from __future__ import annotations

import asyncio
import base64
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from desktop_bridge.models import BridgeEvent
from desktop_bridge.role_tts_settings import RoleTtsSettings
from desktop_bridge.tts_text import TtsSentenceBuffer
from desktop_bridge.voice_models import (
    VoiceOperationMetrics,
    VoiceServiceError,
)
from desktop_bridge.voice_service import VoiceService

logger = logging.getLogger("desktop.bridge.tts")

TtsEventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


class TtsTurnCoordinator:
    """Queues complete reply sentences without blocking chat lifecycle events."""

    def __init__(
        self,
        *,
        voice_service: VoiceService,
        session_key: str,
        request_id: str,
        turn_id: str,
        settings: RoleTtsSettings,
        emit_event: TtsEventEmitter,
    ) -> None:
        self._voice_service = voice_service
        self._session_key = session_key
        self._request_id = request_id
        self._turn_id = turn_id
        self._settings = settings
        self._emit_event = emit_event
        self._buffer = TtsSentenceBuffer()
        self._queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._finished = False
        self._cancelled = False
        self._cancel_event = threading.Event()
        self._sequence = 0

    @property
    def enabled(self) -> bool:
        """Returns whether this role has a usable voice id for the turn."""

        configured_provider = str(
            getattr(self._voice_service, "tts_provider", "") or ""
        ).strip()
        return (
            self._settings.enabled
            and bool(self._settings.voice_id)
            and self._settings.provider == configured_provider
        )

    @property
    def turn_id(self) -> str:
        """Returns the voice turn that owns emitted playback events."""

        return self._turn_id

    def push(self, content_delta: str) -> None:
        """Adds streamed text and schedules any newly completed sentences."""

        if not self.enabled or self._finished or self._cancelled:
            return
        for sentence in self._buffer.push(content_delta):
            self._queue.put_nowait((self._next_sequence(), sentence))
        self._wake.set()
        self._ensure_worker()

    def finish(self) -> None:
        """Flushes the final sentence and lets the worker drain in the background."""

        if self._finished or self._cancelled:
            return
        self._finished = True
        if self.enabled:
            for sentence in self._buffer.finish():
                self._queue.put_nowait((self._next_sequence(), sentence))
            self._wake.set()
            self._ensure_worker()

    async def wait(self) -> None:
        """Waits for queued synthesis, primarily for shutdown and deterministic tests."""

        worker = self._worker
        if worker is not None:
            try:
                await worker
            except asyncio.CancelledError:
                if not self._cancelled:
                    raise

    def cancel(self) -> None:
        """Cancels provider work when the bridge or desktop turn is torn down."""

        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_event.set()
        self._finished = True
        while not self._queue.empty():
            _ = self._queue.get_nowait()
            self._queue.task_done()
        self._wake.set()
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()

    def _next_sequence(self) -> int:
        sequence = self._sequence
        self._sequence += 1
        return sequence

    def _ensure_worker(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name=f"desktop-tts:{self._session_key}")

    async def _run(self) -> None:
        while not self._finished or not self._queue.empty():
            if self._queue.empty():
                self._wake.clear()
                if self._finished and self._queue.empty():
                    break
                await self._wake.wait()
                continue
            sequence, sentence = await self._queue.get()
            try:
                result = await asyncio.to_thread(
                    self._voice_service.stream_synthesize_result,
                    sentence,
                    voice_id=self._settings.voice_id,
                    speed=self._settings.speed,
                    emotion=self._settings.emotion,
                    cancel_event=self._cancel_event,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if isinstance(exc, VoiceServiceError):
                    message = str(exc)
                else:
                    message = "角色语音合成失败"
                metrics = getattr(exc, "metrics", None)
                if not isinstance(metrics, VoiceOperationMetrics):
                    metrics = VoiceOperationMetrics(
                        provider=self._settings.provider,
                        request_id="",
                        elapsed_ms=0,
                        audio_duration_ms=0,
                        character_count=len(sentence),
                        error_code=(
                            getattr(exc, "error_code", "")
                            if isinstance(exc, VoiceServiceError)
                            else "internal_error"
                        )
                        or "provider_error",
                    )
                logger.warning(
                    "tts sentence failed provider=%s session=%s sequence=%d request_id=%s error_code=%s elapsed_ms=%d characters=%d message=%s",
                    metrics.provider,
                    self._session_key,
                    sequence,
                    metrics.request_id,
                    metrics.error_code,
                    metrics.elapsed_ms,
                    metrics.character_count,
                    message,
                )
                await self._emit(
                    BridgeEvent(
                        id=self._request_id,
                        type="event",
                        method="voice.tts.error",
                        payload={
                            "session_key": self._session_key,
                            "request_id": self._request_id,
                            "voice_turn_id": self._turn_id,
                            "sequence": sequence,
                            "message": message,
                            "metrics": metrics.to_dict(),
                        },
                    ).to_dict()
                )
            else:
                await self._emit(
                    BridgeEvent(
                        id=self._request_id,
                        type="event",
                        method="voice.tts.audio",
                        payload={
                            "session_key": self._session_key,
                            "request_id": self._request_id,
                            "voice_turn_id": self._turn_id,
                            "sequence": sequence,
                            "text": sentence,
                            "audio_base64": base64.b64encode(result.audio).decode("ascii"),
                            "format": "mp3",
                            "mood": self._settings.mood,
                            "metrics": result.metrics.to_dict(),
                        },
                    ).to_dict()
                )
            finally:
                self._queue.task_done()
        if not self._cancelled:
            await self._emit(
                BridgeEvent(
                    id=self._request_id,
                    type="event",
                    method="voice.tts.finished",
                    payload={
                        "session_key": self._session_key,
                        "request_id": self._request_id,
                        "voice_turn_id": self._turn_id,
                    },
                ).to_dict()
            )

    async def _emit(self, payload: dict[str, Any]) -> None:
        result = self._emit_event(payload)
        if isinstance(result, Awaitable):
            await result
