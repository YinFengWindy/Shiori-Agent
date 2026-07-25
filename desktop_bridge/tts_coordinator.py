from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from desktop_bridge.models import BridgeEvent
from desktop_bridge.voice_service import TtsSentenceBuffer, VoiceService, VoiceServiceError

logger = logging.getLogger("desktop.bridge.tts")

TtsEventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
MINIMAX_EMOTIONS = frozenset(
    {"happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm", "whisper"}
)


@dataclass(frozen=True)
class RoleTtsSettings:
    """Resolved voice settings for one assistant turn."""

    voice_id: str
    speed: float
    emotion: str
    mood: str


def resolve_role_tts_settings(runtime_config: object, mood: object) -> RoleTtsSettings:
    """Reads role-owned voice data while ignoring malformed optional fields."""

    config = runtime_config if isinstance(runtime_config, dict) else {}
    raw_tts = config.get("tts")
    tts = raw_tts if isinstance(raw_tts, dict) else {}
    voice_id = str(tts.get("voice_id") or "").strip()
    raw_speed = tts.get("speed", 1.0)
    speed = float(raw_speed) if isinstance(raw_speed, (int, float)) else 1.0
    if not 0.5 <= speed <= 2.0:
        speed = 1.0
    mood_name = str(mood or "").strip()
    raw_mapping = tts.get("mood_tts_emotions")
    mapping = raw_mapping if isinstance(raw_mapping, dict) else {}
    candidate = str(mapping.get(mood_name) or "").strip().lower()
    emotion = candidate if candidate in MINIMAX_EMOTIONS else ""
    return RoleTtsSettings(voice_id=voice_id, speed=speed, emotion=emotion, mood=mood_name)


class TtsTurnCoordinator:
    """Queues complete reply sentences without blocking chat lifecycle events."""

    def __init__(
        self,
        *,
        voice_service: VoiceService,
        session_key: str,
        request_id: str,
        settings: RoleTtsSettings,
        emit_event: TtsEventEmitter,
    ) -> None:
        self._voice_service = voice_service
        self._session_key = session_key
        self._request_id = request_id
        self._settings = settings
        self._emit_event = emit_event
        self._buffer = TtsSentenceBuffer()
        self._queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._finished = False
        self._sequence = 0

    @property
    def enabled(self) -> bool:
        """Returns whether this role has a usable voice id for the turn."""

        return bool(self._settings.voice_id)

    def push(self, content_delta: str) -> None:
        """Adds streamed text and schedules any newly completed sentences."""

        if not self.enabled or self._finished:
            return
        for sentence in self._buffer.push(content_delta):
            self._queue.put_nowait((self._next_sequence(), sentence))
        self._wake.set()
        self._ensure_worker()

    def finish(self) -> None:
        """Flushes the final sentence and lets the worker drain in the background."""

        if self._finished:
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
            await worker

    def cancel(self) -> None:
        """Cancels provider work when the bridge or desktop turn is torn down."""

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
                audio = await asyncio.to_thread(
                    self._voice_service.stream_synthesize,
                    sentence,
                    voice_id=self._settings.voice_id,
                    speed=self._settings.speed,
                    emotion=self._settings.emotion,
                )
                await self._emit(
                    BridgeEvent(
                        id=self._request_id,
                        type="event",
                        method="voice.tts.audio",
                        payload={
                            "session_key": self._session_key,
                            "request_id": self._request_id,
                            "sequence": sequence,
                            "text": sentence,
                            "audio_base64": base64.b64encode(audio).decode("ascii"),
                            "format": "mp3",
                            "mood": self._settings.mood,
                        },
                    ).to_dict()
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if isinstance(exc, VoiceServiceError):
                    message = str(exc)
                else:
                    message = "角色语音合成失败"
                logger.warning(
                    "tts sentence failed provider=minimax session=%s sequence=%d message=%s",
                    self._session_key,
                    sequence,
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
                            "sequence": sequence,
                            "message": message,
                        },
                    ).to_dict()
                )
            finally:
                self._queue.task_done()

    async def _emit(self, payload: dict[str, Any]) -> None:
        try:
            result = self._emit_event(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("tts event emission failed session=%s", self._session_key)
