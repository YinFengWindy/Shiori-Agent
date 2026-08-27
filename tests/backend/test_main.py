from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import main as app_main


def test_main_help_prints_usage(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        app_main.main(["--help"])

    assert exc_info.value.code == 0
    assert "bridge" in capsys.readouterr().out


def test_main_accepts_desktop_as_bridge_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    serve_bridge = AsyncMock()
    monkeypatch.setattr(app_main, "serve_bridge", serve_bridge)

    exit_code = app_main.main(["desktop", "--config", str(config_path)])

    assert exit_code == 0
    serve_bridge.assert_awaited_once_with(str(config_path), None)


@pytest.mark.asyncio
async def test_inspect_modules_prints_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    class _Runtime:
        async def inspect_modules(self):
            return {"memory": "ready"}

        async def stop(self):
            return None

    class _HttpResources:
        async def aclose(self):
            return None

    monkeypatch.setattr(app_main.Config, "load", lambda _: object())
    monkeypatch.setattr(app_main, "SharedHttpResources", _HttpResources)
    monkeypatch.setattr(
        "bootstrap.tools.build_core_runtime",
        lambda config, workspace, http_resources: _Runtime(),
    )

    await app_main.inspect_modules(workspace=tmp_path)

    assert "{'memory': 'ready'}" in capsys.readouterr().out
