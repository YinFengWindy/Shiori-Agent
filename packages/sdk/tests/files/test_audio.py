"""PCM checks distinguish complete signal, truncation and digital silence."""

import io
import wave

import pytest
from shiori_sdk.files.audio import pcm_wav_duration


def audio(samples: bytes, width=2):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, width, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(samples)
    return stream.getvalue()


def test_duration_validates_frames_and_signal():
    data = audio(b"\x01\x00" * 16000)
    assert pcm_wav_duration(data, require_signal=True) == 1
    with pytest.raises(ValueError, match="不完整"):
        pcm_wav_duration(data[:-4])


@pytest.mark.parametrize("samples,width", [(b"\x00\x00" * 100, 2), (b"\x80" * 100, 1)])
def test_digital_silence(samples, width):
    data = audio(samples, width)
    assert pcm_wav_duration(data) > 0
    with pytest.raises(ValueError, match="静音"):
        pcm_wav_duration(data, require_signal=True)


@pytest.mark.parametrize("data", [b"", b"not wav", audio(b"")])
def test_empty_or_invalid(data):
    with pytest.raises(ValueError):
        pcm_wav_duration(data)
