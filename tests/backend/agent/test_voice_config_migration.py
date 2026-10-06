"""Voice credentials migrate once and remain owned by each provider plugin."""

import tomllib
from agent.voice_config_migration import migrate_voice_config, voice_plugin_config
from infra.persistence.toml_store import render_toml


def test_migration_preserves_references_settings_and_independent_switches(tmp_path):
    source = {
        "voice": {
            "enabled": True,
            "asr": {
                "enabled": True,
                "provider": "tencent",
                "secret_id": "id",
                "secret_key": "${TENCENT_KEY}",
            },
            "tts": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://custom/",
                "api_key": "${MINIMAX_KEY}",
                "model": "custom",
                "volume": 2.5,
            },
        },
        "plugins": {"minimax_tts": {"enabled": False, "model": "override"}},
    }
    path = tmp_path / "config.toml"
    path.write_text(render_toml(source), encoding="utf-8")
    migrated = migrate_voice_config(path, source)
    assert migrated["plugins"]["tencent_asr"] == {
        "enabled": True,
        "secret_id": "id",
        "secret_key": "${TENCENT_KEY}",
    }
    assert migrated["plugins"]["minimax_tts"] == {
        "enabled": False,
        "model": "override",
        "base_url": "https://custom/",
        "api_key": "${MINIMAX_KEY}",
        "volume": 2.5,
    }
    assert migrated["voice"]["tts"] == {"enabled": True, "provider": "minimax"}
    assert source["voice"]["tts"]["api_key"] == "${MINIMAX_KEY}"
    before = path.read_bytes()
    assert migrate_voice_config(path, migrated) == migrated
    assert path.read_bytes() == before
    assert tomllib.loads(before.decode()) == migrated


def test_switching_selection_never_moves_new_plugin_settings_back():
    source = {
        "voice": {"tts": {"provider": "other"}},
        "plugins": {
            "minimax_tts": {"api_key": "saved"},
            "other": {"endpoint": "local"},
        },
    }
    assert voice_plugin_config(source) == source
