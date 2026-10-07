"""The managed recipe and stored external settings have separate ownership."""

import json
from pathlib import Path

import pytest
from shiori_sdk.managed.paths import native_path

from plugins.gpt_sovits_tts.backend.runtime import create_runtime, effective_settings
from plugins.gpt_sovits_tts.backend.runtime_manifest import INSTALLED_SIZE
from plugins.gpt_sovits_tts.backend.settings import Settings, VoiceStore


def test_managed_unavailable_does_not_fall_back_to_external_url(context, tmp_path):
    runtime = create_runtime(context, VoiceStore(tmp_path))
    external = Settings(url="http://127.0.0.1:9123")
    assert effective_settings(external, runtime) is external
    with pytest.raises(RuntimeError, match="未运行"):
        effective_settings(
            external.model_copy(update={"connection_mode": "managed"}), runtime
        )
    assert runtime.installation.root.is_relative_to(
        native_path(tmp_path / "plugin-data/gpt_sovits_tts")
    )
    assert runtime.installation.installed_size == INSTALLED_SIZE


def test_custom_location_moves_caches_but_not_service_identity(context, tmp_path):
    runtime = create_runtime(context, VoiceStore(tmp_path))
    state = runtime.service.root
    install = tmp_path / "other-drive" / "gpt_sovits_tts-runtime"
    runtime.relocate(install)
    assert runtime.service.root == state
    version = native_path(install) / "v" / "generation"
    command, _cwd, env = runtime.service.launch(version, 12345, "token")
    # Configuration stays in plugin data; temp and model caches follow the install.
    assert native_path(Path(command[-1])) == state / "tts-config.json"
    config = json.loads((state / "tts-config.json").read_text(encoding="utf-8"))
    assert native_path(Path(config["custom"]["t2s_weights_path"])).is_relative_to(
        version
    )
    assert native_path(Path(env["TEMP"])) == native_path(install) / "tmp"
    assert native_path(Path(env["HF_HOME"])) == native_path(install) / "cache/hf_home"
