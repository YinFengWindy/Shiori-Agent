"""Native process capability preserves host ownership before the child may execute."""

import subprocess
from unittest.mock import Mock

import pytest

from agent.plugin_host import processes


@pytest.mark.parametrize("platform,owned", [("win32", True), ("linux", False)])
def test_sync_spawn_uses_existing_host_owned_tree_boundary(
    tmp_path, monkeypatch, platform, owned
):
    child, owner = Mock(), Mock()
    spawn = Mock(return_value=(child, owner))
    monkeypatch.setattr(processes, "popen_owned", spawn)
    monkeypatch.setattr(processes.sys, "platform", platform)
    command = ["node.exe", "index.js"]
    environment = {"NAPCAT_WORKDIR": str(tmp_path)}
    with (tmp_path / "process.log").open("ab") as log:
        result = (
            processes.HostProcesses()
            .as_capability()
            .popen(
                command,
                cwd=tmp_path,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
        assert result == (child, owner)
        spawn.assert_called_once_with(
            command,
            owned=owned,
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
