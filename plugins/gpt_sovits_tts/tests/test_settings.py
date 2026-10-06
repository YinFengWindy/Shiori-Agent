"""Private connection and multi-mood role settings survive restart without host data."""

import pytest
from pydantic import ValidationError
from plugins.gpt_sovits_tts.backend.settings import VoiceStore


def test_private_voice_roundtrip_preserves_two_moods(
    tmp_path, import_reference, references
):
    neutral, happy = import_reference(), import_reference(signal=2)
    voice = references.store.save_role(
        "role",
        {
            "default": {"asset": neutral},
            "moods": {
                "Neutral": {"asset": neutral, "prompt_text": "平静"},
                "Happy": {"asset": happy, "prompt_text": "开心"},
            },
            "speed": 1.2,
            "text_lang": "zh",
        },
    )
    store = VoiceStore(tmp_path)
    assert store.read().roles["role"] == voice
    assert store.path.is_relative_to(tmp_path / "plugin-data/gpt_sovits_tts")
    assert not (tmp_path / "roles.json").exists()
    with pytest.raises(ValidationError):
        store.save_settings({"version": "v5"})
    with pytest.raises(ValidationError):
        store.save_role("role", {"default": {"asset": "../escape.wav"}})
    assert store.read().roles["role"] == voice
