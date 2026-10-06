from pathlib import Path

import pytest

from agent import config


def test_plugin_config_retains_raw_reference_alongside_resolved_value(monkeypatch):
    monkeypatch.setenv("QQBOT_SECRET", "resolved-secret")
    loaded = config.load_config_data(
        {"plugins": {"qqbot": {"client_secret": "${QQBOT_SECRET}"}}}
    )
    assert loaded.plugins["qqbot"]["client_secret"] == "resolved-secret"
    assert loaded.raw_plugin_configs["qqbot"]["client_secret"] == "${QQBOT_SECRET}"


@pytest.mark.parametrize("content", ["", "[llm]\nregistrations = []"])
def test_load_config_accepts_empty_model_registry(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    loaded = config.load_config(path)
    assert loaded.model_registrations == []
    assert loaded.model == ""


def test_load_config_retains_incomplete_registration_for_repair():
    loaded = config.load_config_data(
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                    }
                ]
            }
        }
    )
    assert len(loaded.model_registrations) == 1
    assert loaded.model_registrations[0].model == ""


@pytest.mark.parametrize("registrations", [["invalid"], {}, [{"model": "x"}]])
def test_load_config_rejects_structurally_invalid_registrations(registrations):
    with pytest.raises(ValueError):
        config.load_config_data({"llm": {"registrations": registrations}})


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
    assert loaded.asr.provider == "tencent"
    assert not hasattr(loaded.asr, "secret_id")
    assert not hasattr(loaded.asr, "model")
    assert loaded.tts.provider == "minimax"
    assert not hasattr(loaded.tts, "api_key")


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
def test_load_config_rejects_legacy_root_visual_fields(
    tmp_path: Path, name: str
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
{name} = "legacy"

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "main"
effort = "none"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"配置项已移除: {name}"):
        config.load_config(config_path)


def test_load_config_data_accepts_the_feishu_plugin_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[plugins.feishu] was rejected while the old plugin was removed (#363 T6)."""
    monkeypatch.setenv("FEISHU_TEST_SECRET", "resolved-secret")

    loaded = config.load_config_data(
        {
            "plugins": {
                "feishu": {"app_id": "cli_app", "app_secret": "${FEISHU_TEST_SECRET}"}
            }
        }
    )

    assert loaded.plugins["feishu"] == {
        "app_id": "cli_app",
        "app_secret": "resolved-secret",
    }


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


def _write_minimal_config(tmp_path: Path) -> Path:
    """写一份只含必填项的 config，用于断言各项默认值。"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "test-model"
api_key = "test-key"
effort = "none"

[agent]
system_prompt = "test"
""".strip() + "\n",
        encoding="utf-8",
    )
    return config_path


def test_load_config_keeps_internal_max_iterations_default(tmp_path: Path):
    cfg = config.load_config(_write_minimal_config(tmp_path))

    assert cfg.max_iterations == 10


def test_load_config_defaults_memory_window_and_optimizer_interval(tmp_path: Path):
    cfg = config.load_config(_write_minimal_config(tmp_path))

    assert cfg.memory_window == 40
    assert cfg.memory_optimizer_interval_seconds == 64800
    assert cfg.context_budget.trigger_ratio == 0.75
    assert cfg.context_budget.target_ratio == 0.4
    assert cfg.context_budget.safety_margin_tokens == 4096


def test_load_config_reads_context_budget_policy():
    loaded = config.load_config_data(
        {
            "agent": {
                "context": {
                    "trigger_ratio": 0.8,
                    "target_ratio": 0.5,
                    "safety_margin_tokens": 1234,
                }
            }
        }
    )
    assert loaded.context_budget.trigger_ratio == 0.8
    assert loaded.context_budget.target_ratio == 0.5
    assert loaded.context_budget.safety_margin_tokens == 1234


def test_load_config_upgrades_plugin_markers_but_candidate_parsing_is_pure(
    tmp_path, monkeypatch
):
    import agent.plugin_preferences as preferences

    packages = tmp_path / "plugins"
    marker = packages / "demo/plugin.disabled"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")
    (marker.parent / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    monkeypatch.setattr(preferences, "plugin_roots", lambda: [packages])
    monkeypatch.setattr(preferences, "REPOSITORY_ROOT", tmp_path)
    path = tmp_path / "config.toml"
    path.write_text("[plugins.demo]\nsecret = 'keep'\n", encoding="utf-8")
    before = path.read_bytes()
    assert config.load_config_text(path.read_text(encoding="utf-8")).plugins[
        "demo"
    ] == {"secret": "keep"}
    assert path.read_bytes() == before
    assert config.load_config(path).plugins["demo"] == {
        "secret": "keep",
        "enabled": False,
    }


def test_load_config_resolves_plugin_environment_values(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        '[plugins.qqbot]\napp_id = "qq-app"\nclient_secret = "${QQBOT_SECRET}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QQBOT_SECRET", "qq-secret")
    assert config.load_config(path).plugins["qqbot"] == {
        "app_id": "qq-app",
        "client_secret": "qq-secret",
    }


_REGISTRATION_ID = "12345678-1234-1234-1234-123456789012"


def _registration(**fields):
    return config.load_config_data(
        {"llm": {"registrations": [{"id": _REGISTRATION_ID, **fields}]}}
    ).model_registrations[0]


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5, "128000"])
def test_registration_rejects_invalid_capacity(capacity):
    with pytest.raises(ValueError, match="model_context_window"):
        _registration(model_context_window=capacity)


@pytest.mark.parametrize("limit", [0, -1, 128000, 200000])
def test_registration_rejects_auto_compact_limit_outside_window(limit):
    with pytest.raises(
        ValueError, match="model_auto_compact_token_limit|小于上下文窗口"
    ):
        _registration(model_context_window=128000, model_auto_compact_token_limit=limit)


def test_legacy_capacity_migrates_window_and_drops_output_capability():
    from core.roles.model_errors import incomplete_registration_fields

    legacy = _registration(
        provider="openai",
        model="m",
        api_key="test",
        context_window_tokens=128000,
        max_output_tokens=32768,
    )
    assert legacy.model_context_window == 128000
    assert legacy.model_auto_compact_token_limit is None
    assert not hasattr(legacy, "max_output_tokens")
    assert not incomplete_registration_fields(legacy)
    current = _registration(
        model_context_window=200000, model_auto_compact_token_limit=150000
    )
    assert current.model_auto_compact_token_limit == 150000
    missing = _registration(provider="openai", model="m", api_key="test")
    assert incomplete_registration_fields(missing) == ("model_context_window",)
    # An incomplete registration may keep its threshold until the window is filled.
    pending = _registration(model_auto_compact_token_limit=1000)
    assert pending.model_auto_compact_token_limit == 1000


@pytest.mark.parametrize("value", [0, 2, 7])
def test_compaction_retained_turns_loads_independently_of_memory_window(value):
    from agent.config import load_config_data

    config = load_config_data(
        {
            "agent": {
                "context": {"compaction_retained_turns": value, "memory_window": 40}
            }
        }
    )
    assert config.compaction_retained_turns == value
    assert config.memory_window == 40


@pytest.mark.parametrize("value", [-1, 1.5, True, "2", None])
def test_compaction_retained_turns_rejects_invalid_configuration(value):
    from agent.config import load_config_data

    with pytest.raises(ValueError, match="非负整数"):
        load_config_data({"agent": {"context": {"compaction_retained_turns": value}}})


def test_compaction_retained_turns_defaults_to_two():
    from agent.config import load_config_data

    assert load_config_data({}).compaction_retained_turns == 2


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2000", None])
def test_summary_token_limit_rejects_invalid_configuration(value):
    from agent.config import load_config_data

    with pytest.raises(ValueError, match="正整数"):
        load_config_data({"agent": {"context": {"summary_token_limit": value}}})


def test_summary_token_limit_defaults_and_loads_independently():
    from agent.config import load_config_data

    assert load_config_data({}).summary_token_limit == 2000
    config = load_config_data({"agent": {"context": {"summary_token_limit": 4000}}})
    assert config.summary_token_limit == 4000
    assert config.max_tokens == 8192
    assert config.compaction_retained_turns == 2
    assert config.context_budget.trigger_ratio == 0.75


def test_raw_candidate_maps_legacy_voice_credentials_without_persisting_or_expanding_raw(
    monkeypatch,
):
    monkeypatch.setenv("VOICE_SECRET", "resolved-secret")
    loaded = config.load_config_text(
        '[voice.asr]\nenabled=true\nsecret_key="${VOICE_SECRET}"\n[voice.tts]\nprovider=""\n'
    )
    assert loaded.plugins["tencent_asr"]["secret_key"] == "resolved-secret"
    assert loaded.raw_plugin_configs["tencent_asr"]["secret_key"] == "${VOICE_SECRET}"
    assert loaded.voice.tts.provider == ""
