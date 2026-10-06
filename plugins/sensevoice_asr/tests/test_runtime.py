"""Managed selection is explicit and never borrows an external service endpoint."""

import pytest

from plugins.sensevoice_asr.backend.runtime import create_runtime, effective_settings
from plugins.sensevoice_asr.backend.settings import Settings, SettingsStore


def test_managed_unavailable_does_not_fall_back_to_external_url(context, tmp_path):
    runtime = create_runtime(context, SettingsStore(tmp_path))
    external = Settings(url="http://127.0.0.1:8123")
    assert effective_settings(external, runtime) is external
    with pytest.raises(RuntimeError, match="未运行"):
        effective_settings(
            external.model_copy(update={"connection_mode": "managed"}), runtime
        )
    assert runtime.installation.root.is_relative_to(
        tmp_path / "plugin-data/sensevoice_asr"
    )
