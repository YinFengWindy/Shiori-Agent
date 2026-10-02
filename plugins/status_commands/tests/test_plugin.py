"""SDK-only setup and optional public Observe dependency behavior."""

from types import SimpleNamespace
import pytest
from plugins.status_commands.backend.plugin import setup
from plugins.observe.backend.telemetry import KVCacheTurn
from shiori_sdk.testing.extensions import FakeExtensionContext, FakeDependencies


@pytest.mark.asyncio
async def test_optional_provider_is_resolved_again_for_every_command(command_frame):
    exports = {}
    ctx = FakeExtensionContext(
        "status_commands", dependencies=FakeDependencies(exports)
    )
    await setup(ctx)
    modules = ctx.lifecycle.modules["before_turn"]

    async def reply():
        frame = command_frame("/kvcache")
        for module in modules:
            await module.run(frame)
        return frame.slots["session:ctx"].abort_reply

    assert "KVCache 不可用" in await reply()
    exports["observe"] = SimpleNamespace(
        recent_cache_turns=lambda *a, **kw: (
            KVCacheTurn("reply", "2026-09-11T04:05:00Z", 1000, 800),
        )
    )
    assert "Token  800 / 1,000" in await reply()
    del exports["observe"]
    assert "KVCache 不可用" in await reply()
    exports["observe"] = SimpleNamespace(recent_cache_turns=lambda *a, **kw: ())
    assert await reply() == "暂无 KVCache 数据。"
    assert ctx.bot_commands.commands == [
        ("memorystatus", "查看记忆整理状态"),
        ("kvcache", "查看 KVCache 状态"),
    ]
    await ctx.aclose()
    assert ctx._lifecycle.modules == {} and ctx.bot_commands.commands == []
