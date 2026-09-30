"""A child that cannot join its job is never left running suspended."""

from unittest.mock import Mock

import pytest

from infra.process import owned_spawn


def test_job_failure_kills_the_suspended_child(monkeypatch):
    process = Mock(pid=123)
    popen = Mock(return_value=process)
    monkeypatch.setattr(owned_spawn.subprocess, "Popen", popen)
    monkeypatch.setattr(
        owned_spawn, "WindowsJob", Mock(side_effect=OSError("access denied"))
    )
    with pytest.raises(OSError, match="access denied"):
        owned_spawn.popen_owned(["node.exe"])
    assert popen.call_args.kwargs["creationflags"] == owned_spawn.OWNED_TREE_FLAGS
    process.kill.assert_called_once()
    process.wait.assert_called_once()
