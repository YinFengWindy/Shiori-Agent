from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import main


@pytest.mark.asyncio
async def test_serve_bridge_disables_external_message_channels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    captured: dict[str, object] = {}

    class _Runtime:
        def __init__(self) -> None:
            self.core = SimpleNamespace()

        async def start(self) -> None:
            return None

        async def shutdown(self) -> None:
            return None

    class _BridgeServer:
        def __init__(self, runtime) -> None:
            captured["server_runtime"] = runtime

        async def serve_stdio(self) -> None:
            captured["served"] = True

    def _fake_build_app_runtime(config, *, workspace, features):
        captured["config"] = config
        captured["workspace"] = workspace
        captured["features"] = features
        return _Runtime()

    monkeypatch.setattr(main.Config, "load", staticmethod(lambda _path: object()))
    monkeypatch.setattr(main, "build_app_runtime", _fake_build_app_runtime)
    monkeypatch.setattr(main, "DesktopBridgeServer", _BridgeServer)

    await main.serve_bridge(workspace=tmp_path)

    features = captured["features"]
    assert isinstance(features, main.RuntimeFeatures)
    assert features.start_ipc is False
    assert features.enable_message_channels is False
    assert features.enable_dashboard is False
    assert features.enable_proactive is True
    assert captured["workspace"] == tmp_path
    assert captured["served"] is True
