"""Only decoded formal content may reach chat/TTS consumers."""

import json

import pytest

from agent.core.reply_stream import RoleReplyStream
from core.roles.reply_state import InvalidRoleReply


@pytest.mark.parametrize("content_first", [True, False])
@pytest.mark.parametrize("ensure_ascii", [True, False])
@pytest.mark.parametrize("chunk_size", [1, 2, 7, 25])
async def test_incremental_content_handles_reordering_escapes_and_unicode(
    content_first, ensure_ascii, chunk_size
):
    content = '你好，“我”说："稍等"。\n路径 C:\\名字 🌸'
    fields = {
        "mood": "平静",
        "thought": "我终于放心了。",
        "nested": {"content": "不能展示"},
    }
    fields = (
        {"content": content, **fields}
        if content_first
        else {**fields, "content": content}
    )
    raw = json.dumps(fields, ensure_ascii=ensure_ascii)
    chunks = []

    async def sink(delta):
        chunks.append(delta.get("content_delta", ""))

    stream = RoleReplyStream(sink)
    for index in range(0, len(raw), chunk_size):
        await stream.push({"content_delta": raw[index : index + chunk_size]})
    assert "".join(chunks) == content
    await stream.finish(content)
    assert "".join(chunks) == content
    assert len([chunk for chunk in chunks if chunk]) > 1


async def test_correction_keeps_prefix_and_emits_only_suffix():
    chunks = []

    async def sink(delta):
        chunks.append(delta.get("content_delta", ""))

    stream = RoleReplyStream(sink)
    await stream.push('{"content":"你好')
    assert chunks == ["你好"]
    stream.begin_attempt()
    await stream.push('{"content":"你好，回来啦。","mood":"平静"}')
    await stream.finish("你好，回来啦。")
    assert "".join(chunks) == "你好，回来啦。"
    with pytest.raises(InvalidRoleReply):
        await stream.finish("改写正文")


async def test_plain_text_and_reasoning_cannot_become_formal_content():
    deltas = []

    async def sink(delta):
        deltas.append(delta)

    stream = RoleReplyStream(sink)
    await stream.push({"thinking_delta": 'mood 平静，JSON {"content":"不能展示"}'})
    await stream.push("哼，总算回我了。")
    assert deltas == [{"thinking_delta": 'mood 平静，JSON {"content":"不能展示"}'}]
