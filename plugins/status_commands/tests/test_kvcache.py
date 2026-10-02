"""Command parsing, public query arguments, and unchanged cache report output."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shiori_sdk.testing.extensions import FakeDependencies
from plugins.observe.backend.telemetry import KVCacheTurn


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "limit"),
    [
        ("/kvcache", 5),
        (" /KVCACHE@SomeBot 3 ", 3),
        ("/cache_status 8 extra", 8),
        ("/kvcache invalid", 5),
        ("/kvcache 0", 1),
        ("/kvcache -5", 1),
        ("/kvcache 999", 30),
    ],
)
async def test_cache_command_queries_public_reader_with_bounded_limit(
    backend, command_frame, content, limit
):
    query = Mock(return_value=())
    dependencies = FakeDependencies(
        {"observe": SimpleNamespace(recent_cache_turns=query)}
    )
    frame = command_frame(content)
    await backend.KVCacheCommandModule(dependencies).run(frame)
    query.assert_called_once_with("telegram:1", limit=limit)
    assert frame.slots["session:ctx"].abort_reply == "暂无 KVCache 数据。"


@pytest.mark.asyncio
async def test_cache_report_keeps_totals_per_turn_time_bars_and_previews(
    backend, command_frame
):
    turns = (
        KVCacheTurn(" a reply\nwith spaces ", "2026-09-11T04:05:00Z", 1000, 800),
        KVCacheTurn(
            "[SYSTEM_CONTEXT_FRAME] hidden", "2026-09-11T04:04:00Z", None, None
        ),
    )
    dependencies = FakeDependencies(
        {"observe": SimpleNamespace(recent_cache_turns=Mock(return_value=turns))}
    )
    frame = command_frame("/kvcache")
    await backend.KVCacheCommandModule(dependencies).run(frame)
    assert frame.slots["session:ctx"].abort_reply == (
        "⚡ KVCache · 最近 2 轮\n\n"
        "命中率  80.0%  ████████░░\nToken  800 / 1,000\n\n\n"
        "9-11 12:05   🟢 80.0%  ████████░░\n"
        "    800 / 1,000 tokens\n    a reply with spaces\n\n\n"
        "9-11 12:04   🔴 0.0%  ░░░░░░░░░░\n    0 / 0 tokens"
    )


@pytest.mark.asyncio
async def test_storage_failure_replies_but_programming_errors_propagate(
    backend, command_frame
):
    query = Mock(side_effect=[OSError("read failed"), AttributeError("bad API")])
    dependencies = FakeDependencies(
        {"observe": SimpleNamespace(recent_cache_turns=query)}
    )
    module = backend.KVCacheCommandModule(dependencies)
    frame = command_frame("/kvcache")
    await module.run(frame)
    assert frame.slots["session:ctx"].abort_reply == "KVCache 查询失败。"
    with pytest.raises(AttributeError, match="bad API"):
        await module.run(command_frame("/kvcache"))


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["hello", "/kvcache_extra", "/memorystatus"])
async def test_unrelated_commands_do_not_query_telemetry(
    backend, command_frame, content
):
    dependencies = Mock(spec=FakeDependencies)
    frame = command_frame(content)
    await backend.KVCacheCommandModule(dependencies).run(frame)
    assert "session:ctx" not in frame.slots
    dependencies.get_optional.assert_not_called()


@pytest.mark.asyncio
async def test_prior_abort_is_not_overwritten(backend, command_frame):
    dependencies = Mock(spec=FakeDependencies)
    frame = command_frame("/kvcache")
    previous = object()
    frame.slots["session:ctx"] = previous
    await backend.KVCacheCommandModule(dependencies).run(frame)
    assert frame.slots["session:ctx"] is previous
    dependencies.get_optional.assert_not_called()
