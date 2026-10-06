"""The managed recipe and stored external settings have separate ownership."""

import pytest

from plugins.gpt_sovits_tts.backend.runtime import create_runtime, effective_settings
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
        tmp_path / "plugin-data/gpt_sovits_tts"
    )
