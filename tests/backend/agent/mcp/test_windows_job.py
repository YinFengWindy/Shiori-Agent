"""Windows Job ownership survives a crashing host and includes spawned descendants."""

import ctypes
from ctypes import wintypes
import json
import subprocess
import sys
import time

import pytest

from agent.mcp.windows_job import WindowsJob


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel Job semantics")
def test_host_exit_reaps_assigned_process_without_explicit_cleanup(tmp_path):
    ready = tmp_path / "ready.json"
    owner_code = """import json,subprocess,sys,time
from pathlib import Path
from agent.mcp.windows_job import WindowsJob
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=0x08000004)
job=WindowsJob(child.pid,resume=True)
Path(sys.argv[1]).write_text(json.dumps({'child':child.pid}),encoding='utf-8')
time.sleep(30)
"""
    owner = subprocess.Popen(
        [sys.executable, "-c", owner_code, str(ready)], creationflags=0x08000000
    )
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    child_handle = None
    try:
        deadline = time.monotonic() + 5
        while not ready.is_file():
            assert owner.poll() is None, "Job owner failed to start"
            assert time.monotonic() < deadline, "Job owner readiness timed out"
            time.sleep(0.02)
        pid = json.loads(ready.read_text(encoding="utf-8"))["child"]
        child_handle = kernel.OpenProcess(0x100000, False, pid)
        assert child_handle
        assert kernel.WaitForSingleObject(child_handle, 0) == 258
        owner.terminate()
        owner.wait(timeout=3)
        assert kernel.WaitForSingleObject(child_handle, 3000) == 0
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=3)
        if child_handle:
            kernel.CloseHandle(child_handle)


def test_process_tree_mode_is_explicitly_windows_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows"):
        WindowsJob(1)
