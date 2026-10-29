"""``[plugins.mcp].enabled`` is written once for workspaces with MCP servers."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from bootstrap.mcp_config_migration import migrate_mcp_enabled

_CONFIG = """# 用户的注释
[agent]
max_tokens = 8

[plugins.mcp]
label = "保留"
"""


def _workspace(tmp_path: Path, servers: dict) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "mcp_servers.json").write_text(
        json.dumps({"servers": servers}), encoding="utf-8"
    )
    return workspace


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_bytes(text.encode("utf-8"))
    return path


def test_saved_servers_enable_the_plugin_once_and_keep_the_rest(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, {"fs": {"command": ["fs-server"]}})
    path = _config(tmp_path, _CONFIG)

    migrate_mcp_enabled(path, workspace)
    first = path.read_bytes()
    migrate_mcp_enabled(path, workspace)

    assert path.read_bytes() == first
    text = first.decode("utf-8")
    assert text.startswith("# 用户的注释\n")
    document = tomllib.loads(text)
    assert document["agent"] == {"max_tokens": 8}
    assert document["plugins"]["mcp"] == {"label": "保留", "enabled": True}


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_an_explicit_choice_is_left_alone(tmp_path: Path, enabled: str) -> None:
    workspace = _workspace(tmp_path, {"fs": {"command": ["fs-server"]}})
    text = f"[plugins.mcp]\nenabled = {enabled}\n"
    path = _config(tmp_path, text)

    migrate_mcp_enabled(path, workspace)

    assert path.read_bytes() == text.encode("utf-8")


@pytest.mark.parametrize("servers", [None, {}])
def test_without_saved_servers_the_plugin_stays_off(
    tmp_path: Path, servers: dict | None
) -> None:
    if servers is None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
    else:
        workspace = _workspace(tmp_path, servers)
    path = _config(tmp_path, _CONFIG)

    migrate_mcp_enabled(path, workspace)

    assert path.read_bytes() == _CONFIG.encode("utf-8")
