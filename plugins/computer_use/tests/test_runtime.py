"""Source/frozen location and child environment cannot select a user's Driver."""

import sys

import pytest

from plugins.computer_use.backend.runtime import driver_client, resolve_driver


def test_resolves_only_prepared_components(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "plugins.computer_use.backend.runtime.platform.machine", lambda: "AMD64"
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.runtime.resource_root", lambda: tmp_path
    )
    with pytest.raises(FileNotFoundError, match="prepare:computer-use"):
        resolve_driver()
    root = tmp_path / "native" / "computer-use"
    root.mkdir(parents=True)
    for name in ("cua-driver.exe", "cua-driver-uia.exe"):
        (root / name).write_bytes(b"fixture")
    assert resolve_driver() == root / "cua-driver.exe"
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows x64"):
        resolve_driver()


def test_child_environment_is_private_and_direct(tmp_path, monkeypatch):
    monkeypatch.setenv("CUA_DRIVER_SOCKET", "foreign")
    monkeypatch.setenv("CUA_DRIVER_RS_PERMISSION_MODE", "unrestricted")
    client = driver_client(tmp_path / "data", tmp_path / "driver.exe")
    assert client.command == [str(tmp_path / "driver.exe"), "mcp", "--direct"]
    assert "CUA_DRIVER_SOCKET" not in client.env
    assert "CUA_DRIVER_RS_PERMISSION_MODE" not in client.env
    assert client.env["CUA_DRIVER_RS_UPDATE_CHECK"] == "0"
    assert client.env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] == "0"
    assert client.env["USERPROFILE"] == str(tmp_path / "data")
    assert client._own_process_tree and not client._inherit_env
