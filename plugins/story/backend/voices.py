"""Character voice audio synthesized by the renderer and cached inside one Story."""

from __future__ import annotations

import base64
import binascii

VOICE_FORMATS = frozenset({"wav", "mp3"})


def decode_voice_audio(value: object) -> bytes:
    """Strictly decode renderer-provided audio; partial or empty audio is rejected."""

    if not isinstance(value, str):
        raise ValueError("audio_base64 必须是字符串")
    try:
        audio = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("audio_base64 不是有效的 base64") from exc
    if not audio:
        raise ValueError("audio_base64 不能为空")
    return audio


def encode_voice_audio(audio: bytes) -> str:
    """Encode cached audio for the renderer bridge."""

    return base64.b64encode(audio).decode("ascii")


def voice_relative_path(beat_id: str, fragment_index: int, audio_format: str) -> str:
    """Return the Story-directory-relative file of one cached dialogue fragment."""

    return f"assets/voices/{beat_id}-{fragment_index}.{audio_format}"
