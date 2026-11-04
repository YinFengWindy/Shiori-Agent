"""Source reads use the provider's current export and preserve structured results."""

from types import SimpleNamespace
import pytest
from shiori_sdk.testing.extensions import FakeDependencies
from shiori_sdk.tools import ToolResult
from plugins.proactive.backend.mcp_sources import McpClientPool


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
