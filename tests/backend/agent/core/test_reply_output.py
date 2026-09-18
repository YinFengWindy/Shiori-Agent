"""Role output compatibility must preserve dialogue and ordinary JSON examples."""

import json
from itertools import permutations

import pytest

from agent.core.reply_output import RoleReplyOutput, normalize_role_content


@pytest.mark.parametrize("keys", list(permutations(("content", "mood", "thought"))))
def test_normalize_role_content_accepts_any_field_order(keys):
    content = '（轻声）"回来了。"\n🌸 {雨伞} \\ 放这里。'
    fields = {"content": content, "mood": "平静", "thought": "我放心了。"}
    raw = json.dumps({key: fields[key] for key in keys}, ensure_ascii=False)

    assert normalize_role_content(raw) == content


def test_encoded_trailing_space_does_not_decode_entities_in_dialogue():
    raw = '{"content":"示例 &#x20; &quot;","mood":"平静","thought":"我知道。"}&#x20; '

    assert normalize_role_content(raw) == "示例 &#x20; &quot;"


@pytest.mark.parametrize(
    "raw",
    [
        '她说："回来了。"\n🌸 {雨伞}',
        '{"content":"正常 JSON 示例"}',
        '{"content":"示例","mood":"平静"}',
        '{"content":"示例","mood":"平静","thought":"我知道。","example":true}',
        '{"content":{"nested":true},"mood":"平静","thought":"我知道。"}',
        '{"content":"示例","mood":null,"thought":"我知道。"}',
        '{"content":"第一段","content":"第二段","mood":"平静","thought":"我知道。"}',
        '{"content":"截断的正文',
        '{"content":"引号"错误","mood":"平静","thought":"我知道。"}',
        '例子：{"content":"示例","mood":"平静","thought":"我知道。"}',
        '{"content":"示例","mood":"平静","thought":"我知道。"}\n以上是示例。',
        '```json\n{"content":"正常 JSON 示例"}\n```',
        '```python\n{"content":"示例","mood":"平静","thought":"我知道。"}\n```',
        "`inline code` 和正常正文",
        " \n ",
    ],
)
async def test_unrelated_or_malformed_content_is_preserved_in_stream_and_final(raw):
    emitted = []

    async def sink(delta):
        emitted.append(delta.get("content_delta", ""))

    output = RoleReplyOutput(sink, enabled=True)
    assert output.callback is not None
    for character in raw:
        await output.callback({"content_delta": character})

    assert await output.finish(raw) == raw
    assert "".join(emitted) == raw


async def test_plain_dialogue_and_thinking_stream_before_response_completes():
    emitted = []

    async def sink(delta):
        emitted.append(delta)

    output = RoleReplyOutput(sink, enabled=True)
    assert output.callback is not None
    await output.callback({"thinking_delta": "先思考"})
    assert emitted == [{"thinking_delta": "先思考"}]
    await output.callback({"content_delta": "回来了，"})
    assert emitted[-1] == {"content_delta": "回来了，"}
    await output.callback({"content_delta": "快进来。", "thinking_delta": "继续思考"})
    assert emitted[-1] == {"content_delta": "快进来。", "thinking_delta": "继续思考"}

    assert await output.finish("回来了，快进来。") == "回来了，快进来。"
    assert len(emitted) == 3


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 1024])
async def test_legacy_envelope_is_withheld_while_thinking_passes_through(chunk_size):
    raw = ' \n```json\n{"content":"回来了。","mood":"平静","thought":"我放心了。"}\n```'
    emitted = []

    async def sink(delta):
        emitted.append(delta)

    output = RoleReplyOutput(sink, enabled=True)
    assert output.callback is not None
    for offset in range(0, len(raw), chunk_size):
        await output.callback({"content_delta": raw[offset : offset + chunk_size]})
        assert emitted == []
    await output.callback({"thinking_delta": "主调用思考", "content_delta": "\n"})
    assert emitted == [{"thinking_delta": "主调用思考"}]

    assert await output.finish(raw) == "回来了。"
    assert emitted == [
        {"thinking_delta": "主调用思考"},
        {"content_delta": "回来了。"},
    ]


async def test_complete_response_reaches_sink_when_provider_emits_no_deltas():
    emitted = []

    async def sink(delta):
        emitted.append(delta)

    raw = '{"content":"回来了。","mood":"平静","thought":"我放心了。"}'
    output = RoleReplyOutput(sink, enabled=True)

    assert await output.finish(raw) == "回来了。"
    assert emitted == [{"content_delta": "回来了。"}]


async def test_non_role_call_keeps_its_original_callback_and_json():
    async def sink(_delta):
        pass

    raw = '{"content":"示例","mood":"平静","thought":"我知道。"}'
    output = RoleReplyOutput(sink, enabled=False)

    assert output.callback is sink
    assert await output.finish(raw) == raw
