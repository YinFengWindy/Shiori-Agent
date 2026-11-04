"""Source reads use the provider's current export and preserve structured results."""

import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from shiori_sdk.testing.extensions import FakeDependencies
from shiori_sdk.tools import ToolResult
from plugins.proactive.backend.mcp_sources import (
    McpClientPool,
    fetch_context_data_async,
)


async def test_source_resolves_reloaded_provider_and_refuses_disabled_provider():
    dependencies = FakeDependencies()

    async def first(*args, **kwargs):
        return ToolResult(text="display text", structured_content={"generation": 1})

    async def replacement(*args, **kwargs):
        return '{"generation": 2}'

    dependencies.exports["mcp"] = SimpleNamespace(call=first)
    source = McpClientPool(dependencies=lambda: dependencies)
    assert await source.call("server", "get_context", {}) == {"generation": 1}
    dependencies.exports["mcp"] = SimpleNamespace(call=replacement)
    assert await source.call("server", "get_context", {}) == {"generation": 2}
    dependencies.exports.clear()
    with pytest.raises(RuntimeError, match="未启用"):
        await source.call("server", "get_context", {})


async def test_context_source_uses_export_when_mcp_private_files_are_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Only the owner may read server configuration and credential files."""
    private = tmp_path / "plugin-data" / "mcp"
    (private / "credentials").mkdir(parents=True)
    (private / "mcp_servers.json").write_text(
        "invalid-private-config", encoding="utf-8"
    )
    (private / "credentials" / "token.json").write_text(
        "private-token", encoding="utf-8"
    )
    legacy = tmp_path / "mcp_servers.json"
    legacy.write_text("invalid-legacy-config", encoding="utf-8")
    (tmp_path / "proactive_sources.json").write_text(
        json.dumps({"sources": [{"server": "weather", "channel": "context"}]}),
        encoding="utf-8",
    )
    read_text = Path.read_text

    def public_read(path: Path, *args, **kwargs):
        assert path != legacy and not path.is_relative_to(
            private
        ), "Proactive read another plugin's private data"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", public_read)

    async def current_context(*args, **kwargs):
        return ToolResult(structured_content={"temperature": 20})

    dependencies = FakeDependencies({"mcp": SimpleNamespace(call=current_context)})
    source = McpClientPool(tmp_path, dependencies=lambda: dependencies)
    assert await fetch_context_data_async(source) == [
        {"temperature": 20, "_source": "weather"}
    ]
