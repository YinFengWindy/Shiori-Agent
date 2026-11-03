"""Command arguments, public query arguments, and unchanged cache report output."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "limit"),
    [
        ("/kvcache", 5),
        (" /KVCACHE@SomeBot 3 ", 3),
        ("/kvcache 999", 30),
    ],
)
async def test_cache_command_queries_public_reader_with_bounded_limit(
    plugin, content, limit
):
    query = Mock(return_value=())
    plugin.exports["observe"] = SimpleNamespace(recent_cache_turns=query)
    assert await plugin.answer(content) == "暂无 KVCache 数据。"
    query.assert_called_once_with("telegram:1", limit=limit)


@pytest.mark.asyncio
async def test_storage_failure_replies_but_programming_errors_propagate(plugin):
    query = Mock(side_effect=[OSError("read failed"), AttributeError("bad API")])
    plugin.exports["observe"] = SimpleNamespace(recent_cache_turns=query)
    assert await plugin.answer("/kvcache") == "KVCache 查询失败。"
    with pytest.raises(AttributeError, match="bad API"):
        await plugin.answer("/kvcache")
