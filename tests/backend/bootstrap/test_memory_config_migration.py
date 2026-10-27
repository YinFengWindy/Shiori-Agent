"""Legacy ``[memory]`` migration edges. ``Config.load`` itself is covered in test_wiring."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from agent.config import load_config_text
from bootstrap.memory_config_migration import (
    EMBEDDING_API_KEY_KEY,
    EMBEDDING_BASE_URL_KEY,
    EMBEDDING_MODEL_KEY,
    OUTPUT_DIMENSIONALITY_KEY,
    migrate_legacy_memory_config,
)
from plugins.default_memory.backend.config import DefaultMemoryPluginConfig


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _plugin(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["plugins"]["default_memory"]


def test_missing_enabled_inside_memory_disables_the_plugin(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        '[memory.embedding]\nmodel = "m"\napi_key = "k"\nbase_url = "https://embed.example"\n',
    )

    migrate_legacy_memory_config(path)

    plugin = _plugin(path)
    assert plugin["enabled"] is False
    assert plugin[EMBEDDING_MODEL_KEY] == "m"
    assert plugin[EMBEDDING_API_KEY_KEY] == "k"
    assert plugin[EMBEDDING_BASE_URL_KEY] == "https://embed.example"
    assert "memory" not in tomllib.loads(path.read_text(encoding="utf-8"))


def test_explicit_embedding_wins_over_chat_credentials(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[memory.embedding]
model = "embed"
api_key = "embed-key"
base_url = "https://embed.example/v1"
output_dimensionality = 1536

[llm.fast]
api_key = "fast-key"
base_url = "https://fast.example/v1"

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "chat"
api_key = "primary-key"
base_url = " https://primary.example/v1 "
""",
    )

    migrate_legacy_memory_config(path)

    plugin = _plugin(path)
    assert plugin["enabled"] is True
    assert plugin[EMBEDDING_MODEL_KEY] == "embed"
    assert plugin[EMBEDDING_API_KEY_KEY] == "embed-key"
    assert plugin[EMBEDDING_BASE_URL_KEY] == "https://embed.example/v1"
    assert plugin[OUTPUT_DIMENSIONALITY_KEY] == 1536


def test_empty_embedding_model_stays_empty(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, '[memory]\nenabled = true\n\n[memory.embedding]\nmodel = ""\n')

    migrate_legacy_memory_config(path)

    assert _plugin(path)[EMBEDDING_MODEL_KEY] == ""


def test_empty_embedding_credentials_fall_back_to_llm_fast(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[llm.fast]
api_key = "fast-key"
base_url = "https://fast.example/v1"

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
api_key = "primary-key"
base_url = "https://primary.example/v1"
""",
    )

    migrate_legacy_memory_config(path)

    plugin = _plugin(path)
    assert plugin[EMBEDDING_API_KEY_KEY] == "fast-key"
    assert plugin[EMBEDDING_BASE_URL_KEY] == "https://fast.example/v1"


def test_empty_embedding_credentials_fall_back_to_the_primary_model(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
api_key = "primary-key"
base_url = " https://primary.example/v1 "
""",
    )

    migrate_legacy_memory_config(path)

    plugin = _plugin(path)
    assert plugin[EMBEDDING_API_KEY_KEY] == "primary-key"
    assert plugin[EMBEDDING_BASE_URL_KEY] == "https://primary.example/v1"


def test_embedding_api_key_reference_is_materialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIORI_TEST_EMBED_KEY", "from-env")
    monkeypatch.setattr("agent.config.resolve_default_workspace", lambda: tmp_path)
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[memory.embedding]
api_key = "${SHIORI_TEST_EMBED_KEY}"

[llm.fast]
api_key = "fast-key"
""",
    )

    migrate_legacy_memory_config(path)

    text = path.read_text(encoding="utf-8")
    assert _plugin(path)[EMBEDDING_API_KEY_KEY] == "from-env"
    assert "${SHIORI_TEST_EMBED_KEY}" not in text


def test_unresolved_embedding_reference_does_not_fall_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SHIORI_TEST_UNSET_EMBED_KEY", raising=False)
    monkeypatch.setattr("agent.config.resolve_default_workspace", lambda: tmp_path)
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[memory.embedding]
api_key = "${SHIORI_TEST_UNSET_EMBED_KEY}"

[llm.fast]
api_key = "fast-key"
""",
    )

    migrate_legacy_memory_config(path)

    assert _plugin(path)[EMBEDDING_API_KEY_KEY] == "${SHIORI_TEST_UNSET_EMBED_KEY}"


def test_non_positive_dimensionality_raises_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    text = "[memory]\nenabled = true\n\n[memory.embedding]\noutput_dimensionality = 0\n"
    _write(path, text)

    with pytest.raises(ValueError, match="output_dimensionality"):
        migrate_legacy_memory_config(path)

    assert path.read_text(encoding="utf-8") == text


def test_legacy_enabled_overwrites_plugin_enabled_and_keeps_other_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = false

[memory.embedding]
api_key = "from-memory"

[plugins.default_memory]
enabled = true
note = "stay"
output_dimensionality = 768
""",
    )

    migrate_legacy_memory_config(path)

    plugin = _plugin(path)
    assert plugin["enabled"] is False
    assert plugin["note"] == "stay"
    assert plugin[EMBEDDING_API_KEY_KEY] == "from-memory"
    assert OUTPUT_DIMENSIONALITY_KEY not in plugin


def test_legacy_enabled_true_overrides_an_explicit_plugin_disable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[memory]
enabled = true

[plugins.default_memory]
enabled = false
""",
    )

    migrate_legacy_memory_config(path)

    assert _plugin(path)["enabled"] is True


def test_non_default_engine_is_logged_and_not_stored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.toml"
    _write(path, '[memory]\nenabled = true\nengine = "memu"\n')

    with caplog.at_level("WARNING"):
        migrate_legacy_memory_config(path)

    assert "engine" not in _plugin(path)
    assert any("memu" in record.message for record in caplog.records)


def test_second_migration_does_not_revert_a_later_plugin_edit(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "[memory]\nenabled = false\n")
    migrate_legacy_memory_config(path)
    edited = path.read_text(encoding="utf-8").replace(
        "enabled = false", "enabled = true", 1
    )
    _write(path, edited)

    migrate_legacy_memory_config(path)

    assert _plugin(path)["enabled"] is True


def test_file_without_memory_table_is_left_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    text = "# keep\n[agent]\nmax_tokens = 8\n"
    _write(path, text)

    migrate_legacy_memory_config(path)

    assert path.read_text(encoding="utf-8") == text


def test_unrelated_comment_and_table_survive_header_migration(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """# keep me
[agent]
max_tokens = 8

[memory]
enabled = true

[memory.embedding]
model = "m"
api_key = "k"
""",
    )

    migrate_legacy_memory_config(path)

    text = path.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert text.startswith("# keep me")
    assert parsed["agent"]["max_tokens"] == 8
    assert "memory" not in parsed
    assert parsed["plugins"]["default_memory"][EMBEDDING_API_KEY_KEY] == "k"


def test_inline_memory_table_is_removed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        'memory = { enabled = true, embedding = { model = "m", api_key = "k" } }\n',
    )

    migrate_legacy_memory_config(path)

    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert "memory" not in parsed
    assert parsed["plugins"]["default_memory"][EMBEDDING_API_KEY_KEY] == "k"
    assert parsed["plugins"]["default_memory"]["enabled"] is True


def test_inline_plugin_table_conflict_still_migrates(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[plugins]
default_memory = { enabled = true, note = "stay" }

[memory]
enabled = false
""",
    )

    migrate_legacy_memory_config(path)

    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    plugin = parsed["plugins"]["default_memory"]
    assert "memory" not in parsed
    assert plugin["enabled"] is False
    assert plugin["note"] == "stay"


def test_load_config_text_does_not_apply_the_legacy_memory_table() -> None:
    cfg = load_config_text("[memory]\nenabled = false\n")

    assert not hasattr(cfg, "memory")
    assert cfg.plugins == {}


def test_plugin_config_fields_match_the_host_migration_keys() -> None:
    assert set(DefaultMemoryPluginConfig.model_fields) == {
        EMBEDDING_MODEL_KEY,
        EMBEDDING_API_KEY_KEY,
        EMBEDDING_BASE_URL_KEY,
        OUTPUT_DIMENSIONALITY_KEY,
    }
