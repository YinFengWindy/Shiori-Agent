"""Per-account NapCat process and private login data isolation."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from unittest.mock import AsyncMock, Mock

import pytest
import qrcode

from plugins.qq.backend import managed_napcat
from plugins.qq.backend.managed_napcat import ManagedNapCat
from plugins.qq.backend.napcat_process_guard import ProcessInfo


@pytest.mark.asyncio
async def test_per_account_ports_profiles_and_logout_are_isolated(
    monkeypatch, tmp_path
):
    manager = ManagedNapCat(tmp_path)
    official_qq = tmp_path / "official-qq" / "resources" / "app"
    monkeypatch.setattr(
        manager, "prepare", lambda: asyncio.sleep(0, result=official_qq)
    )
    manager.install_dir.mkdir(parents=True)
    first = "a" * 32
    second = "b" * 32
    launched = []

    def popen(command, **kwargs):
        process = Mock()
        process.poll.return_value = None
        process.pid = len(launched) + 100
        process.wait.return_value = 0
        launched.append((command, kwargs, process))
        return process

    monkeypatch.setattr(managed_napcat.subprocess, "Popen", popen)
    monkeypatch.setattr(managed_napcat.subprocess, "run", Mock())
    monkeypatch.setattr(managed_napcat, "WindowsJob", Mock())
    await manager.start(first, "101")
    await manager.start(second, "202")
    assert len(launched) == 2
    a, b = (row[1]["env"] for row in launched)
    assert a["NAPCAT_WORKDIR"] != b["NAPCAT_WORKDIR"]
    assert a["PATH"].split(os.pathsep)[:2] == [
        str(manager.install_dir),
        str(official_qq),
    ]
    assert b["PATH"].split(os.pathsep)[:2] == [
        str(manager.install_dir),
        str(official_qq),
    ]
    assert a["APPDATA"] != b["APPDATA"]
    assert a["TEMP"] != b["TEMP"]
    assert a["NAPCAT_WEBUI_JWT_SECRET_KEY"] != b["NAPCAT_WEBUI_JWT_SECRET_KEY"]
    assert a["NAPCAT_WEBUI_PREFERRED_PORT"] != b["NAPCAT_WEBUI_PREFERRED_PORT"]
    assert launched[0][1]["cwd"] == manager._files.account_dir(first)
    assert launched[1][1]["cwd"] == manager._files.account_dir(second)
    assert manager.endpoint(first)[0] != manager.endpoint(second)[0]
    assert (
        json.loads(
            (
                manager._files.account_dir(first) / "napcat/config/onebot11_101.json"
            ).read_text(encoding="utf-8")
        )["network"]["websocketServers"][0]["token"]
        == manager.endpoint(first)[1]
    )
    assert (
        json.loads(
            (manager._files.account_dir(first) / "napcat/config/webui.json").read_text(
                encoding="utf-8"
            )
        )["host"]
        == "127.0.0.1"
    )

    first_login = (
        manager._files.account_dir(first) / "profile/AppData/Roaming/Tencent/QQNT"
    )
    second_login = (
        manager._files.account_dir(second) / "profile/AppData/Roaming/Tencent/QQNT"
    )
    first_login.mkdir(parents=True)
    second_login.mkdir(parents=True)
    (first_login / "session").write_text("first", encoding="utf-8")
    (second_login / "session").write_text("second", encoding="utf-8")
    await manager.logout(first)
    assert not first_login.exists()
    assert (second_login / "session").read_text(encoding="utf-8") == "second"
    assert (manager._files.account_dir(first) / "runtime.json").is_file()
    assert (manager._files.account_dir(first) / "napcat/config/onebot11.json").is_file()
    assert second in manager._processes
    await manager.stop_all()


@pytest.mark.asyncio
async def test_managed_status_uses_official_png_instead_of_scan_url(
    monkeypatch, tmp_path
):
    manager = ManagedNapCat(tmp_path)
    ref = "c" * 32
    process = Mock()
    process.poll.return_value = None
    manager._processes[ref] = process
    scan_url = "https://ssl.ptlogin2.qq.com/ptqrlogin?token=account-c"
    image = io.BytesIO()
    qrcode.make(scan_url).save(image)
    qr_path = manager._files.account_dir(ref) / "napcat/cache/qrcode.png"
    qr_path.parent.mkdir(parents=True)
    qr_path.write_bytes(image.getvalue())
    monkeypatch.setattr(
        manager._webui,
        "login_status",
        AsyncMock(
            return_value={"phase": "login_required", "qrcode": scan_url, "error": ""}
        ),
    )
    status = await manager.login_status(ref)
    assert status["qrcode"].startswith("data:image/png;base64,")
    assert base64.b64decode(status["qrcode"].partition(",")[2]) == image.getvalue()
    assert scan_url not in status["qrcode"]

    manager._webui.login_status.return_value = {
        "phase": "online",
        "qrcode": scan_url,
        "error": "",
    }
    assert (await manager.login_status(ref))["qrcode"] == ""
    assert not qr_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("old_image_present", [False, True])
async def test_refresh_rejects_missing_or_stale_png(
    monkeypatch, tmp_path, old_image_present
):
    manager = ManagedNapCat(tmp_path)
    ref = "d" * 32
    if old_image_present:
        image = io.BytesIO()
        qrcode.make("old-url").save(image)
        qr_path = manager._files.account_dir(ref) / "napcat/cache/qrcode.png"
        qr_path.parent.mkdir(parents=True)
        qr_path.write_bytes(image.getvalue())
    manager._qr.image_uri(ref, "old-url")
    monkeypatch.setattr(
        manager._webui,
        "refresh_qrcode",
        AsyncMock(return_value={"qrcode": "new-url", "restarting": False}),
    )
    monkeypatch.setattr(managed_napcat.asyncio, "sleep", AsyncMock())
    with pytest.raises(RuntimeError, match="缺失或仍是旧图"):
        await manager.refresh_qrcode(ref)


def _occupied_port_manager(monkeypatch, tmp_path, processes):
    """Launch-ready manager whose ports stay taken until a process tree is killed."""
    manager = ManagedNapCat(tmp_path)
    monkeypatch.setattr(
        manager, "prepare", lambda: asyncio.sleep(0, result=tmp_path / "qq")
    )
    launched = Mock()
    killed = []
    monkeypatch.setattr(managed_napcat.subprocess, "Popen", launched)
    monkeypatch.setattr(managed_napcat, "WindowsJob", Mock())
    guard = managed_napcat.guard
    monkeypatch.setattr(guard, "port_bindable", lambda _port: bool(killed))
    monkeypatch.setattr(guard, "listener_pid", lambda _port: 11)
    monkeypatch.setattr(guard, "process_info", lambda pid: processes.get(pid))
    monkeypatch.setattr(guard, "kill_process_tree", killed.append)
    return manager, launched, killed


@pytest.mark.asyncio
async def test_orphaned_managed_tree_is_killed_from_its_launcher(monkeypatch, tmp_path):
    # An older install version still counts as this plugin's NapCat.
    node = tmp_path / "managed-napcat" / "v4.0.0" / "node.exe"
    processes = {
        5: ProcessInfo(5, "explorer.exe", tmp_path / "explorer.exe", 1, 1.0),
        10: ProcessInfo(10, "node.exe", node, 5, 2.0),
        11: ProcessInfo(11, "node.exe", node, 10, 3.0),
    }
    manager, launched, killed = _occupied_port_manager(monkeypatch, tmp_path, processes)
    await manager.start("e" * 32, "101")
    assert killed == [10]
    launched.assert_called_once()


@pytest.mark.asyncio
async def test_port_held_by_foreign_process_is_reported_not_killed(
    monkeypatch, tmp_path
):
    foreign = tmp_path / "elsewhere" / "node.exe"
    processes = {11: ProcessInfo(11, "node.exe", foreign, 5, 3.0)}
    manager, launched, killed = _occupied_port_manager(monkeypatch, tmp_path, processes)
    with pytest.raises(RuntimeError, match=r"已被占用（PID 11 node.exe）"):
        await manager.start("f" * 32, "101")
    assert killed == []
    launched.assert_not_called()
