"""Speech settings belong to the desktop pet private files across restarts."""

import json
import pytest
from pydantic import ValidationError
from plugins.desktop_pet.backend.voice_preferences import VoicePreferencesStore


def test_preferences_restart_without_touching_host_or_role_documents(tmp_path):
    config = tmp_path / "config.toml"
    roles = tmp_path / "roles/roles.json"
    config.write_text('[voice]\nlegacy_key="untouched"\n', encoding="utf-8")
    roles.parent.mkdir()
    roles.write_text('{"roles": []}', encoding="utf-8")
    before = (config.read_bytes(), roles.read_bytes())
    store = VoicePreferencesStore(tmp_path)
    assert store.read().enabled is False
    values = {
        "enabled": True,
        "hotkey": "Alt+V",
        "microphone_device_id": "device",
        "asr": {"plugin_id": "neutral", "service_id": "asr"},
        "tts": None,
    }
    store.write(values)
    assert VoicePreferencesStore(tmp_path).read().model_dump() == values
    assert json.loads(store.path.read_text(encoding="utf-8")) == values
    assert store.path == tmp_path / "plugin-data/desktop_pet/voice-preferences.json"
    assert (config.read_bytes(), roles.read_bytes()) == before


def test_invalid_settings_do_not_replace_saved_preferences(tmp_path):
    store = VoicePreferencesStore(tmp_path)
    store.write({"hotkey": "Ctrl+V"})
    with pytest.raises(ValidationError):
        store.write({"enabled": "yes"})
    assert store.read().hotkey == "Ctrl+V"
    store.path.write_text("broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        store.read()


def test_replies_are_spoken_only_when_enabled_with_a_tts_service(tmp_path):
    store = VoicePreferencesStore(tmp_path)
    assert store.read().speech_on is False
    assert store.write({"enabled": True}).speech_on is False
    tts = {"plugin_id": "neutral", "service_id": "tts"}
    assert store.write({"enabled": False, "tts": tts}).speech_on is False
    assert store.write({"enabled": True, "tts": tts}).speech_on is True
