"""Initialization must not replace migrated plugin files with empty defaults."""

from bootstrap.init_workspace import init_workspace


def test_initialization_preserves_existing_plugin_data(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    servers = b'{"servers":{"docs":{"command":["docs-server"]}}}'
    jobs = b'[{"id":"existing-job"}]'
    (workspace / "mcp_servers.json").write_bytes(servers)
    (workspace / "schedules.json").write_bytes(jobs)

    init_workspace(config_path=tmp_path / "config.toml", workspace=workspace)

    assert (workspace / "plugin-data/mcp/mcp_servers.json").read_bytes() == servers
    assert (workspace / "plugin-data/schedule/schedules.json").read_bytes() == jobs
    assert not (workspace / "mcp_servers.json").exists()
    assert not (workspace / "schedules.json").exists()
