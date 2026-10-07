"""Managed selection is explicit and never borrows an external service endpoint."""

from pathlib import Path

import pytest
from shiori_sdk.managed.paths import native_path

from plugins.sensevoice_asr.backend.runtime import create_runtime, effective_settings
from plugins.sensevoice_asr.backend.runtime_manifest import INSTALLED_SIZE
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
        native_path(tmp_path / "plugin-data/sensevoice_asr")
    )
    assert runtime.installation.installed_size == INSTALLED_SIZE


def test_custom_location_holds_every_child_cache_removal_deletes(context, tmp_path):
    runtime = create_runtime(context, SettingsStore(tmp_path))
    install = native_path(tmp_path / "other-drive" / "sensevoice_asr-runtime")
    runtime.relocate(install)
    _command, _cwd, env = runtime.service.launch(install / "v/generation", 1, "t")
    for key in ("TEMP", "UV_CACHE_DIR", "HF_HOME", "MODELSCOPE_CACHE", "TORCH_HOME"):
        assert native_path(Path(env[key])).parent == install
    created = {path.name for path in install.iterdir()}
    assert created <= set(runtime.installation.entries)
    runtime.installation.remove()
    assert not install.exists()
