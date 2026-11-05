"""Cold-start upgrades preserve persisted data and never revive archived state."""

import json
from pathlib import Path

import pytest

from bootstrap.plugin_data_paths import migrate_plugin_data_paths
from plugins.mcp.backend.store import ServerStore
from shiori_sdk.storage import plugin_data_dir
from plugins.proactive.backend.traces import append_loop_trace
from plugins.scene.backend.state import SceneStateStore
from plugins.schedule.backend.scheduler import SchedulerService


def _write(workspace: Path, relative: str, content: bytes) -> Path:
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_upgrade_preserves_data_for_the_actual_consumers(tmp_path: Path):
    """The five legacy files remain readable and subsequent writes use new paths."""
    old_schedule = tmp_path / "schedules.json"
    job = SchedulerService(old_schedule).create_job(
        name="提醒",
        tier="instant",
        trigger="after",
        when="1h",
        content="喝水",
        timezone_name="UTC",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
    )
    scene = {
        "scene_awareness_sessions": {
            "role:mira": {"scene_key": "书房", "visual_key": "desk"}
        }
    }
    servers = {
        "servers": {"docs": {"command": ["docs-server"], "env": {"LANG": "中文"}}}
    }
    _write(tmp_path, "scene/state.json", json.dumps(scene).encode())
    _write(tmp_path, "mcp_servers.json", json.dumps(servers).encode())
    for name in ("proactive_config_trace.jsonl", "proactive_rate_trace.jsonl"):
        _write(tmp_path, f"memory/{name}", b'{"old":true}\n')
    originals = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }

    migrate_plugin_data_paths(tmp_path)
    migrate_plugin_data_paths(tmp_path)

    assert SceneStateStore(tmp_path).current("role:mira")["scene_key"] == "书房"
    scheduler = SchedulerService(tmp_path / "plugin-data/schedule/schedules.json")
    assert scheduler.store.load()[0].id == job.id
    mcp_path = plugin_data_dir(tmp_path, "mcp") / "mcp_servers.json"
    mcp = ServerStore(mcp_path)
    mcp.load()
    config = mcp.servers["docs"]
    credentials = mcp.credentials(config)
    assert credentials.command == servers["servers"]["docs"]["command"]
    assert credentials.env == servers["servers"]["docs"]["env"]
    assert config.enabled and config.tools.mode == "all"
    persisted = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 2
    assert "env" not in persisted["servers"]["docs"]
    reloaded = ServerStore(mcp_path)
    reloaded.load()
    assert reloaded.credentials(reloaded.servers["docs"]) == credentials
    append_loop_trace(
        tmp_path, "proactive_rate_trace.jsonl", {"interval": 30}, role_id="mira"
    )
    log = tmp_path / "plugin-data/proactive/logs/proactive_rate_trace.jsonl"
    records = [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0] == {"old": True}
    assert records[1]["payload"] == {"interval": 30}
    for relative, content in originals.items():
        assert not (tmp_path / relative).exists()
        copies = list(
            (
                tmp_path / "private_runtime/plugin-storage-archive" / relative
            ).parent.glob(f"{relative.name}.*.bak")
        )
        assert len(copies) == 1 and copies[0].read_bytes() == content


def test_existing_empty_target_wins_and_archive_is_never_reimported(tmp_path: Path):
    source = _write(tmp_path, "scene/state.json", b'{"old":"state"}')
    target = _write(tmp_path, "plugin-data/scene/state.json", b"{}")

    migrate_plugin_data_paths(tmp_path)
    assert target.read_bytes() == b"{}"
    assert not source.exists()
    target.unlink()  # Explicitly clearing plugin data must not revive the backup.
    migrate_plugin_data_paths(tmp_path)
    assert not target.exists()


def test_archive_failure_preserves_source_and_retry_preserves_newer_target(
    tmp_path: Path, monkeypatch
):
    import bootstrap.plugin_data_paths as migration

    source = _write(tmp_path, "schedules.json", b"[]")
    save = migration.atomic_save_bytes

    def fail_archive(path, content):
        if "plugin-storage-archive" in path.parts:
            raise OSError("archive unavailable")
        save(path, content)

    monkeypatch.setattr(migration, "atomic_save_bytes", fail_archive)
    with pytest.raises(OSError, match="archive unavailable"):
        migrate_plugin_data_paths(tmp_path)
    assert source.read_bytes() == b"[]"
    target = _write(tmp_path, "plugin-data/schedule/schedules.json", b'[{"new":true}]')
    monkeypatch.setattr(migration, "atomic_save_bytes", save)
    migrate_plugin_data_paths(tmp_path)
    assert target.read_bytes() == b'[{"new":true}]'
    assert not source.exists()


def test_invalid_legacy_state_stops_before_publishing_or_removing_source(
    tmp_path: Path,
):
    source = _write(tmp_path, "scene/state.json", b"[]")
    with pytest.raises(ValueError, match="格式无效"):
        migrate_plugin_data_paths(tmp_path)
    assert source.read_bytes() == b"[]"
    assert not (tmp_path / "plugin-data/scene/state.json").exists()
