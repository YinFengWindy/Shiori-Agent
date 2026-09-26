"""QQ host TOML retirement only follows the plugin's private copy receipt."""

from __future__ import annotations

import tomllib
import json

from agent.legacy_config_receipt import legacy_config_digest
from agent.qq_host_config_migration import retire_copied_qq_config


def test_retire_copied_qq_config_keeps_other_plugin_and_enabled(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[plugins.qq]\nbot_uin = "123"\nws_uri = "ws://127.0.0.1:3001"\n'
        'ws_token = "secret"\nenabled = false\n\n[plugins.other]\nkey = "keep"\n',
        encoding="utf-8",
    )
    before = tomllib.loads(path.read_text(encoding="utf-8"))
    assert retire_copied_qq_config(path, before, workspace=tmp_path) == before
    assert 'ws_token = "secret"' in path.read_text(encoding="utf-8")

    receipt = tmp_path / "plugin-data" / "qq" / "legacy-host-config.migrated.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "source_hash": legacy_config_digest(
                    {
                        "bot_uin": "123",
                        "ws_uri": "ws://127.0.0.1:3001",
                        "ws_token": "secret",
                        "websocket_open_timeout_seconds": 5.0,
                    }
                ),
            }
        ),
        encoding="utf-8",
    )
    changed = path.read_text(encoding="utf-8").replace("secret", "new-secret")
    path.write_text(changed, encoding="utf-8")
    newer = tomllib.loads(changed)
    assert retire_copied_qq_config(path, newer, workspace=tmp_path) == newer
    assert "new-secret" in path.read_text(encoding="utf-8")
    path.write_text(
        path.read_text(encoding="utf-8").replace("new-secret", "secret"),
        encoding="utf-8",
    )
    retired = retire_copied_qq_config(path, before, workspace=tmp_path)
    assert retired["plugins"]["qq"] == {"enabled": False}
    assert retired["plugins"]["other"] == {"key": "keep"}
    assert retire_copied_qq_config(path, retired, workspace=tmp_path) == retired
    assert "secret" not in path.read_text(encoding="utf-8")


def test_qq_config_receipt_matches_resolved_reference_without_leaking_it(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHIORI_TEST_QQ_TOKEN", "resolved-secret")
    path = tmp_path / "config.toml"
    path.write_text(
        '[plugins.qq]\nbot_uin = "123"\nws_token = "${SHIORI_TEST_QQ_TOKEN}"\n',
        encoding="utf-8",
    )
    receipt = tmp_path / "plugin-data" / "qq" / "legacy-host-config.migrated.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "source_hash": legacy_config_digest(
                    {
                        "bot_uin": "123",
                        "ws_uri": "",
                        "ws_token": "resolved-secret",
                        "websocket_open_timeout_seconds": 5.0,
                    }
                ),
            }
        ),
        encoding="utf-8",
    )
    assert "resolved-secret" not in receipt.read_text(encoding="utf-8")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    retired = retire_copied_qq_config(path, data, workspace=tmp_path)
    assert "qq" not in retired["plugins"]
    assert "resolved-secret" not in path.read_text(encoding="utf-8")
