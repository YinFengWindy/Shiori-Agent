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


def test_load_config_rejects_legacy_model_sections(tmp_path: Path) -> None:
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

    with pytest.raises(ValueError, match=r"配置项已移除: \[llm.vl\]"):
        config.load_config(config_path)


@pytest.mark.parametrize("name", ["vl_model", "vl_api_key", "vl_base_url"])
def test_load_config_rejects_legacy_root_visual_fields(tmp_path: Path, name: str) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'''\
{name} = "legacy"

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "main"
effort = "none"
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"配置项已移除: {name}"):
        config.load_config(config_path)


def test_load_config_ignores_retired_registration_names(tmp_path: Path) -> None:
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

    loaded = config.load_config(config_path)

    assert [item.model for item in loaded.model_registrations] == ["first", "second"]
    assert all(not hasattr(item, "name") for item in loaded.model_registrations)


def test_load_config_reads_desktop_chat_streaming_switch(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "main"
effort = "none"

[agent]
system_prompt = "system"

[desktop.chat]
streaming_enabled = true
""".strip(),
        encoding="utf-8",
    )

    loaded = config.load_config(config_path)

    assert loaded.desktop_streaming_enabled is True
