"""Only orphaned trees from the managed NapCat install are ever killed."""

from __future__ import annotations

import os
import subprocess
import sys

import psutil
import pytest

from plugins.qq.backend import napcat_process_guard as guard
from plugins.qq.backend.napcat_process_guard import ProcessInfo


def _occupied_port(monkeypatch, processes):
    """Port 9 stays taken by PID 11 until some process tree is killed."""
    killed = []
    monkeypatch.setattr(guard, "port_bindable", lambda _port: bool(killed))
    monkeypatch.setattr(guard, "listener_pid", lambda _port: 11)
    monkeypatch.setattr(guard, "process_info", lambda pid: processes.get(pid))
    monkeypatch.setattr(guard, "kill_process_tree", killed.append)
    return killed


def _managed_tree(root, bridge=None):
    """Launcher PID 10 and listener PID 11 from an older install version."""
    node = root / "v4.0.0" / "node.exe"
    processes = {
        10: ProcessInfo(10, "node.exe", node, 5, 2.0),
        11: ProcessInfo(11, "node.exe", node, 10, 3.0),
    }
    if bridge is not None:
        processes[5] = bridge
    return processes


@pytest.mark.parametrize("bridge_create_time", [None, 9.0])
async def test_orphaned_tree_is_killed_from_its_launcher(
    monkeypatch, tmp_path, bridge_create_time
):
    # The bridge PID 5 is either gone or reused by a process newer than the
    # launcher; both mean the launcher is an orphan.
    bridge = None
    if bridge_create_time is not None:
        bridge = ProcessInfo(
            5, "chrome.exe", tmp_path / "chrome.exe", 1, bridge_create_time
        )
    processes = _managed_tree(tmp_path / "managed-napcat", bridge)
    killed = _occupied_port(monkeypatch, processes)
    await guard.reclaim_port(9, tmp_path / "managed-napcat")
    assert killed == [processes[10]]


async def test_tree_with_live_bridge_is_left_to_its_owner(monkeypatch, tmp_path):
    bridge = ProcessInfo(5, "python.exe", tmp_path / "python.exe", 1, 1.0)
    killed = _occupied_port(
        monkeypatch, _managed_tree(tmp_path / "managed-napcat", bridge)
    )
    with pytest.raises(RuntimeError, match=r"另一个运行中的 Shiori 占用（PID 5）"):
        await guard.reclaim_port(9, tmp_path / "managed-napcat")
    assert killed == []


@pytest.mark.parametrize(
    "exe", ["elsewhere/node.exe", None], ids=["foreign", "access-denied"]
)
async def test_foreign_or_uninspectable_owner_is_reported_not_killed(
    monkeypatch, tmp_path, exe
):
    image = tmp_path / exe if exe else None
    killed = _occupied_port(
        monkeypatch, {11: ProcessInfo(11, "node.exe", image, 5, 3.0)}
    )
    with pytest.raises(RuntimeError, match=r"已被占用（PID 11 node.exe）"):
        await guard.reclaim_port(9, tmp_path / "managed-napcat")
    assert killed == []


def test_kill_skips_a_pid_whose_identity_changed():
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        real = psutil.Process(child.pid).create_time()
        stale = ProcessInfo(child.pid, "python", None, os.getpid(), real - 60)
        guard.kill_process_tree(stale)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()
