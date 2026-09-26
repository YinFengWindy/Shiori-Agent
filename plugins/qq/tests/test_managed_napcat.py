"""Per-account NapCat process and private login data isolation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest

from plugins.qq.backend import managed_napcat
from plugins.qq.backend.managed_napcat import ManagedNapCat


@pytest.mark.asyncio
async def test_per_account_ports_profiles_and_logout_are_isolated(
    monkeypatch, tmp_path
):
    manager = ManagedNapCat(tmp_path)
    monkeypatch.setattr(manager, "prepare", lambda: asyncio.sleep(0))
    monkeypatch.setattr(manager, "_check_native_dependencies", lambda: None)
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
    await manager.start(first, "101")
    await manager.start(second, "202")
    assert len(launched) == 2
    a, b = (row[1]["env"] for row in launched)
    assert a["NAPCAT_WORKDIR"] != b["NAPCAT_WORKDIR"]
    assert a["APPDATA"] != b["APPDATA"]
    assert a["TEMP"] != b["TEMP"]
    assert a["NAPCAT_WEBUI_JWT_SECRET_KEY"] != b["NAPCAT_WEBUI_JWT_SECRET_KEY"]
    assert a["NAPCAT_WEBUI_PREFERRED_PORT"] != b["NAPCAT_WEBUI_PREFERRED_PORT"]
    assert launched[0][1]["cwd"] == manager._account_dir(first)
    assert launched[1][1]["cwd"] == manager._account_dir(second)
    assert manager.endpoint(first)[0] != manager.endpoint(second)[0]
    assert (
        json.loads(
            (manager._account_dir(first) / "napcat/config/onebot11_101.json").read_text(
                encoding="utf-8"
            )
        )["network"]["websocketServers"][0]["token"]
        == manager.endpoint(first)[1]
    )
    assert (
        json.loads(
            (manager._account_dir(first) / "napcat/config/webui.json").read_text(
                encoding="utf-8"
            )
        )["host"]
        == "127.0.0.1"
    )

    first_login = manager._account_dir(first) / "profile/AppData/Roaming/Tencent/QQNT"
    second_login = manager._account_dir(second) / "profile/AppData/Roaming/Tencent/QQNT"
    first_login.mkdir(parents=True)
    second_login.mkdir(parents=True)
    (first_login / "session").write_text("first", encoding="utf-8")
    (second_login / "session").write_text("second", encoding="utf-8")
    await manager.logout(first)
    assert not first_login.exists()
    assert (second_login / "session").read_text(encoding="utf-8") == "second"
    assert (manager._account_dir(first) / "runtime.json").is_file()
    assert (manager._account_dir(first) / "napcat/config/onebot11.json").is_file()
    assert second in manager._processes
    await manager.stop_all()


def test_missing_official_native_dependencies_fail_before_process_start(
    monkeypatch, tmp_path
):
    manager = ManagedNapCat(tmp_path)
    manager.install_dir.mkdir(parents=True)
    monkeypatch.setattr(managed_napcat.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="crypto.dll, ssl.dll"):
        manager._check_native_dependencies()
