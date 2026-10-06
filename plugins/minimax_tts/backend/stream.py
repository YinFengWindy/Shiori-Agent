"""Decode MiniMax SSE audio frames and respect caller cancellation."""

from __future__ import annotations
import base64
import binascii
import json
import threading
from collections.abc import Callable, Iterable, Iterator
from typing import Any
from shiori_sdk.voice import VoiceServiceError


def parse_minimax_stream_chunks(
    chunks: Iterable[bytes],
    *,
    on_payload: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[bytes]:
    """Decodes newline-delimited MiniMax JSON/``data:`` audio chunks."""

    pending = b""
    for chunk in chunks:
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield from _parse_minimax_stream_line(line, on_payload=on_payload)
    if pending.strip():
        yield from _parse_minimax_stream_line(pending, on_payload=on_payload)


def _cancelable_stream_chunks(
    chunks: Iterable[bytes],
    cancel_event: threading.Event | None,
) -> Iterator[bytes]:
    for chunk in chunks:
        if cancel_event is not None and cancel_event.is_set():
            raise VoiceServiceError("语音合成已取消", error_code="cancelled")
        yield chunk
    if cancel_event is not None and cancel_event.is_set():
        raise VoiceServiceError("语音合成已取消", error_code="cancelled")


def _parse_minimax_stream_line(
    line: bytes,
    *,
    on_payload: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[bytes]:
    text = line.decode("utf-8", errors="replace").strip()
    if not text or text == "[DONE]":
        return
    if text.startswith("data:"):
        text = text[5:].strip()
    if text == "[DONE]":
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VoiceServiceError("MiniMax TTS 流式响应格式无效") from exc
    if not isinstance(payload, dict):
        raise VoiceServiceError("MiniMax TTS 流式响应格式无效")
    if on_payload is not None:
        on_payload(payload)
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, dict) and base_resp.get("status_code", 0) not in (0, None):
        raise VoiceServiceError(
            str(base_resp.get("status_msg") or "MiniMax TTS 请求失败"),
            error_code=str(base_resp.get("status_code") or ""),
            request_id=str(payload.get("trace_id") or "").strip(),
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    raw_audio = data.get("audio")
    if not isinstance(raw_audio, str) or not raw_audio:
        return
    yield _decode_audio_string(raw_audio)


def _decode_audio_string(raw_audio: str) -> bytes:
    try:
        return bytes.fromhex(raw_audio)
    except ValueError:
        try:
            return base64.b64decode(raw_audio, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VoiceServiceError("MiniMax TTS 音频数据无效") from exc
