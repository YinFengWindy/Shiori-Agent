"""Small PCM WAV checks without a decoder or inference runtime dependency."""

import io
import wave


def pcm_wav_duration(data: bytes, *, require_signal: bool = False) -> float:
    """Validate complete PCM WAV frames and optionally reject digital silence."""
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            width = audio.getsampwidth()
            count = audio.getnframes()
            if audio.getframerate() <= 0 or audio.getnchannels() <= 0:
                raise ValueError("WAV 音频参数无效")
            frames = audio.readframes(count)
            expected = count * audio.getnchannels() * width
            if not count or len(frames) != expected:
                raise ValueError("WAV 音频为空或不完整")
            silence = 128 if width == 1 else 0
            if require_signal and all(value == silence for value in frames):
                raise ValueError("WAV 音频为全零静音；请检查推理服务日志与参考音频")
            return count / audio.getframerate()
    except (wave.Error, EOFError) as error:
        raise ValueError("需要完整的 PCM WAV 音频") from error
