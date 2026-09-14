"""Host assembly and storage initialization select exactly one memory engine."""

from pathlib import Path
import shutil
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from agent.config_models import Config
from agent.provider import LLMProvider
from agent.tools.registry import ToolRegistry
from bootstrap.memory import build_memory_runtime, ensure_memory_plugin_storage
from bootstrap.paths import REPOSITORY_ROOT
from core.net.http import HttpRequester, SharedHttpResources
from session.store import SessionStore


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["default", "akasha"])
async def test_real_selected_engine_assembles_without_loading_the_other(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    engine: str,
):
    plugin_root = tmp_path / "plugins"
    package = "default_memory" if engine == "default" else engine
    other = "akasha" if engine == "default" else "default_memory"
    backend = plugin_root / package / "backend"
    _ = shutil.copytree(
        REPOSITORY_ROOT / "plugins" / package / "backend",
        backend,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    _ = (backend / "config.local.toml").write_text("", encoding="utf-8")
    unselected = plugin_root / other / "backend"
    unselected.mkdir(parents=True)
    _ = (unselected / "memory_plugin.py").write_text(
        "raise AssertionError('unselected engine loaded')", encoding="utf-8"
    )
    monkeypatch.setattr("bootstrap.memory_plugins.plugin_roots", lambda: [plugin_root])
    monkeypatch.setitem(sys.modules, "plugins", None)
    monkeypatch.chdir(tmp_path)
    request = AsyncMock(side_effect=AssertionError("assembly must not request models"))
    monkeypatch.setattr(HttpRequester, "request", request)
    provider = Mock(spec=LLMProvider)
    provider.chat = AsyncMock(side_effect=AssertionError("assembly must not chat"))
    config = Config(provider="openai", model="test", api_key="test")
    config.memory.enabled = True
    config.memory.engine = engine
    workspace = tmp_path / "workspace"
    selected_db = (
        workspace / "memory" / ("memory2.db" if engine == "default" else "akasha.db")
    )
    other_db = (
        workspace / "memory" / ("akasha.db" if engine == "default" else "memory2.db")
    )

    storage = ensure_memory_plugin_storage(config, workspace)
    assert storage == [(selected_db, False)]
    assert selected_db.is_file()
    assert not other_db.exists()
    assert ensure_memory_plugin_storage(config, workspace) == [(selected_db, True)]
    # Normal host startup creates sessions first; Akasha then builds its FTS IDF.
    sessions = SessionStore(workspace / "sessions.db")
    sessions.close()

    http = SharedHttpResources()
    try:
        runtime = build_memory_runtime(
            config, workspace, ToolRegistry(), provider, None, http
        )
        try:
            assert runtime.engine.describe().name == engine
            assert len(runtime.closeables) == 2
            assert not other_db.exists()
            engine_file = sys.modules[type(runtime.engine).__module__].__file__
            assert engine_file is not None
            assert Path(engine_file).is_relative_to(backend)
            request.assert_not_called()
            provider.chat.assert_not_called()
            assert capsys.readouterr().out == ""
        finally:
            await runtime.aclose()
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_disabled_memory_does_not_resolve_or_initialize_an_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def unexpected_resolve(_name: str):
        raise AssertionError("disabled memory must not load an engine")

    monkeypatch.setattr("bootstrap.wiring.resolve_memory_plugin", unexpected_resolve)
    config = Config(provider="openai", model="test", api_key="test")
    config.memory.enabled = False
    assert ensure_memory_plugin_storage(config, tmp_path) == []
    http = SharedHttpResources()
    try:
        runtime = build_memory_runtime(
            config, tmp_path, ToolRegistry(), Mock(spec=LLMProvider), None, http
        )
        assert runtime.engine.describe().name == "disabled"
        assert runtime.closeables == []
    finally:
        await http.aclose()
