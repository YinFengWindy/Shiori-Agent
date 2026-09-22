from __future__ import annotations

import asyncio

import pytest

from agent.tools.shell import _MAX_OUTPUT, _truncate
from agent.tools.shell.output import _read_output


def test_truncate_keeps_tail_and_drops_head_when_over_limit():
    truncated = _truncate("HEAD\n" + ("a" * 31000) + "\nTAIL")

    assert truncated["truncated"] is True
    assert truncated["strategy"] == "tail"
    assert "HEAD" not in truncated["text"]
    assert "TAIL" in truncated["text"]
    assert len(truncated["text"]) <= _MAX_OUTPUT


@pytest.mark.asyncio
async def test_read_output_preserves_utf8_across_chunk_boundaries():
    stream = asyncio.StreamReader()
    text = "你好😀"
    chunks = []

    async def read():
        async for chunk in _read_output(stream):
            chunks.append(chunk)

    reader = asyncio.create_task(read())
    for byte in text.encode("utf-8"):
        stream.feed_data(bytes([byte]))
        await asyncio.sleep(0)
    stream.feed_eof()
    await reader
    assert "".join(chunks) == text


@pytest.mark.asyncio
async def test_read_output_flushes_incomplete_utf8_at_eof():
    stream = asyncio.StreamReader()
    stream.feed_data("好".encode("utf-8")[:-1])
    stream.feed_eof()
    assert [chunk async for chunk in _read_output(stream)] == ["�"]
