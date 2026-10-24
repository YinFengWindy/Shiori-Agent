"""SDK-only setup and optional public Observe dependency behavior."""

from types import SimpleNamespace

import pytest

from plugins.observe.backend.telemetry import KVCacheTurn


@pytest.mark.asyncio
async def test_optional_provider_is_resolved_again_for_every_command(plugin):
    exports = plugin.exports
    assert await plugin.answer("/kvcache") == (
        "KVCache 不可用（observe 未安装、未启用或未提供遥测接口）。"
    )
    exports["observe"] = SimpleNamespace(
        recent_cache_turns=lambda *a, **kw: (
            KVCacheTurn("reply", "2026-09-11T04:05:00Z", 1000, 800),
        )
    )
    reply = await plugin.answer("/kvcache")
    assert reply is not None and "Token  800 / 1,000" in reply
    del exports["observe"]
    reply = await plugin.answer("/kvcache")
    assert reply is not None and "KVCache 不可用" in reply
    exports["observe"] = SimpleNamespace(recent_cache_turns=lambda *a, **kw: ())
    assert await plugin.answer("/kvcache") == "暂无 KVCache 数据。"


@pytest.mark.asyncio
async def test_menu_lists_described_commands_and_unload_removes_all(plugin):
    assert plugin.commands.menu() == [
        ("memorystatus", "查看记忆整理状态"),
        ("kvcache", "查看 KVCache 状态"),
    ]
    await plugin.ctx.aclose()
    assert plugin.commands.menu() == []
    assert plugin.commands.handler("/memory_status") is None
    assert plugin.commands.handler("/cache_status") is None
