"""Private preferences are restart-readable and CPU-only."""

import pytest
from pydantic import ValidationError
from plugins.sensevoice_asr.backend.settings import SettingsStore


def test_private_settings_round_trip(tmp_path):
    store = SettingsStore(tmp_path)
    saved = store.write(
        {"url": "http://127.0.0.1:8123", "device": "cpu", "model": "sensevoice"}
    )
    assert SettingsStore(tmp_path).read() == saved
    assert store.path.is_relative_to(tmp_path / "plugin-data/sensevoice_asr")
    with pytest.raises(ValidationError):
        store.write({"device": "cuda"})
    assert store.read() == saved
