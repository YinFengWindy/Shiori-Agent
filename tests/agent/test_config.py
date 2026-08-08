from pathlib import Path

import pytest

from agent import config


def test_resolve_reads_unexpanded_value_from_default_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "API_TOKEN").write_text("secret", encoding="utf-8")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(config, "resolve_default_workspace", lambda: workspace)

    assert config._resolve("${API_TOKEN}") == "secret"


def test_load_voice_config_reads_global_provider_and_input_settings() -> None:
    loaded = config._load_voice_config(
        {
            "voice": {
                "enabled": True,
                "hotkey": "Alt+V",
                "microphone_device_id": "device-1",
                "asr": {"secret_id": "id", "secret_key": "key", "model": "ignored"},
                "tts": {"api_key": "tts-key", "volume": 2.5},
            }
        }
    )

    assert loaded.enabled is True
    assert loaded.hotkey == "Alt+V"
    assert loaded.microphone_device_id == "device-1"
    assert loaded.asr.secret_id == "id"
    assert not hasattr(loaded.asr, "model")
    assert loaded.tts.api_key == "tts-key"
    assert loaded.tts.volume == 2.5


def test_load_config_migrates_legacy_models_to_stable_registrations(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "deepseek"

[llm.main]
model = "deepseek-chat"
api_key = "main-key"
base_url = "https://api.deepseek.com/v1"
enable_thinking = true

[llm.fast]
model = "deepseek-fast"

[llm.vl]
model = "vision-model"

[agent]
system_prompt = "system"
""".strip(),
        encoding="utf-8",
    )

    first = config.load_config(config_path)
    second = config.load_config(config_path)

    assert [item.name for item in first.model_registrations] == [
        "主模型",
        "轻量模型",
        "视觉模型",
    ]
    assert first.model_registrations[0].effort == "high"
    assert [item.id for item in first.model_registrations] == [
        item.id for item in second.model_registrations
    ]


def test_load_config_rejects_duplicate_registration_names(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
name = "same"
provider = "openai"
model = "first"
effort = "none"

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000002"
name = "Same"
provider = "openai"
model = "second"
effort = "low"

[agent]
system_prompt = "system"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="模型注册名称重复"):
        config.load_config(config_path)
