"""Native process capability preserves host ownership before the child may execute."""

import subprocess
import asyncio
import os
import signal
import sys
from unittest.mock import Mock

import pytest

from infra.process import plugin_capability as processes


@pytest.mark.skipif(sys.platform != "win32", reason="Windows tree ownership contract")
async def test_unowned_client_does_not_adopt_its_application_child(tmp_path):
    marker = tmp_path / "child-ready"
    child_source = (
        "import time; from pathlib import Path; "
        f"Path({str(marker)!r}).write_text('ready'); time.sleep(30)"
    )
    client_source = (
        "import subprocess,sys; "
        f"p=subprocess.Popen([sys.executable,'-c',{child_source!r}], "
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,flush=True)"
    )
    client, owner = await processes.HostProcesses().spawn(
        sys.executable,
        "-c",
        client_source,
        env=dict(os.environ),
        cwd=str(tmp_path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        own_process_tree=False,
    )
    stdout, stderr = await client.communicate()
    assert client.returncode == 0, stderr
    child_pid = int(stdout)
    try:
        assert owner is None
        async with asyncio.timeout(5):
            while not marker.exists():
                await asyncio.sleep(0.02)
        # The client is gone; its external application is still running.
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, child_pid)
        assert handle
        try:
            code = wintypes.DWORD()
            assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            assert code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    finally:
        os.kill(child_pid, signal.SIGTERM)


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
        result = processes.HostProcesses().popen(
            command,
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
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
