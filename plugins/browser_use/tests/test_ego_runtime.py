"""User installation discovery cannot silently fall back from explicit settings."""

import pytest

from plugins.browser_use.backend import ego_runtime as module
from plugins.browser_use.backend.ego_runtime import EgoRuntime


def test_missing_explicit_executable_does_not_use_path_program(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "win32")
    valid = tmp_path / "ego-browser.exe"
    valid.write_bytes(b"client")
    monkeypatch.setattr(module.shutil, "which", lambda _: str(valid))
    with pytest.raises(FileNotFoundError, match="ego-browser"):
        EgoRuntime.resolve(str(tmp_path / "missing.exe"))


def test_windows_install_location_works_with_stale_process_path(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    executable = tmp_path / ".local/share/ego/active_version_dir/ego-browser.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"client")
    assert EgoRuntime.resolve().executable == executable.resolve()
