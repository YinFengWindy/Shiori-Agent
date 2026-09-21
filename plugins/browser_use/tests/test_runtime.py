"""Native path lookup never borrows programs from the system or another checkout."""

import pytest

from plugins.browser_use.backend import runtime as module
from plugins.browser_use.backend.runtime import BrowserRuntime


def test_source_and_packaged_roots_share_native_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "resource_root", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="prepare:browser-use"):
        BrowserRuntime.resolve()
    root = tmp_path / "native" / "browser-use"
    (root / "chrome-win64").mkdir(parents=True)
    (root / "agent-browser.exe").write_bytes(b"fixed native")
    (root / "chrome-win64" / "chrome.exe").write_bytes(b"fixed browser")
    runtime = BrowserRuntime.resolve()
    assert runtime.agent_browser == root / "agent-browser.exe"
    assert runtime.chrome == root / "chrome-win64" / "chrome.exe"


def test_unsupported_platform_fails_before_resource_lookup(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows"):
        BrowserRuntime.resolve()
