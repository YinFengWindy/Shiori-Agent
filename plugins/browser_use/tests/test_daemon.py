"""Daemon startup deadlines and failure cleanup do not depend on native downloads."""

from unittest.mock import AsyncMock, Mock

import pytest

from plugins.browser_use.backend import daemon as module
from plugins.browser_use.backend.daemon import BrowserDaemon


def environment(tmp_path):
    return {
        "AGENT_BROWSER_SOCKET_DIR": str(tmp_path / "run"),
        "AGENT_BROWSER_NAMESPACE": "test",
        "AGENT_BROWSER_SESSION": "owned",
    }


async def test_live_process_without_listening_socket_times_out_and_is_reaped(
    tmp_path, monkeypatch
):
    process = Mock(pid=123, returncode=None)
    process.wait = AsyncMock(return_value=0)
    monkeypatch.setattr(
        module.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    job = Mock()
    monkeypatch.setattr(module, "WindowsJob", Mock(return_value=job))
    daemon = BrowserDaemon(tmp_path / "fixed.exe", tmp_path, environment(tmp_path))
    with pytest.raises(TimeoutError):
        await daemon.start(0.03)
    job.close.assert_called_once()
    process.kill.assert_called_once()
    assert daemon._process is daemon._job is daemon._log is None


async def test_job_failure_still_closes_log_and_reaps_process(tmp_path, monkeypatch):
    process = Mock(pid=123, returncode=None)
    process.wait = AsyncMock(return_value=0)
    daemon = BrowserDaemon(tmp_path / "fixed.exe", tmp_path, environment(tmp_path))
    daemon._process = process
    daemon._job = Mock()
    daemon._job.close.side_effect = RuntimeError("job failure")
    log = (tmp_path / "daemon.log").open("w+b")
    daemon._log = log
    with pytest.raises(RuntimeError, match="job failure"):
        await daemon.close()
    process.kill.assert_called_once()
    assert log.closed


async def test_existing_session_fingerprint_is_never_adopted(tmp_path):
    env = environment(tmp_path)
    socket = tmp_path / "run" / "namespaces" / "test" / "run"
    socket.mkdir(parents=True)
    marker = socket / "owned.config"
    marker.write_text("existing", encoding="utf-8")
    daemon = BrowserDaemon(tmp_path / "fixed.exe", tmp_path, env)
    with pytest.raises(FileExistsError):
        await daemon.start(1)
    assert marker.read_text(encoding="utf-8") == "existing"
