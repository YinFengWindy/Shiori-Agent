from __future__ import annotations

import json

import pytest
from shiori_sdk.testing import FakeFrame, FakePluginContext

from shiori_sdk.lifecycle import ResponseMetadata
from shiori_sdk.lifecycle import AfterReasoningCtx


from plugins.citation.backend.plugin import (
    CitationAfterReasoningModule,
    ProtocolTagCleanupModule,
    extract_cited_ids,
    extract_cited_ids_from_tool_chain,
    strip_trailing_protocol_tags,
    strip_inline_memory_refs,
    setup,
)


def test_citation_extracts_ascii_marker_only_at_end() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[mem_1,mem-2]§")

    assert clean == "答复正文"
    assert ids == ["mem_1", "mem-2"]


def test_citation_extracts_model_marker_without_terminator() -> None:
    clean, ids = extract_cited_ids("§cited:[9b615a9c5f29,7e190efce6ff]")

    assert clean == ""
    assert ids == ["9b615a9c5f29", "7e190efce6ff"]


def test_citation_extracts_marker_with_spaces_after_commas() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[mem_1, mem-2]§")

    assert clean == "答复正文"
    assert ids == ["mem_1", "mem-2"]


def test_citation_extracts_colon_message_ids() -> None:
    clean, ids = extract_cited_ids(
        "答复正文\n§cited:[telegram:7674283004:4395,telegram:7674283004:4396]§"
    )

    assert clean == "答复正文"
    assert ids == ["telegram:7674283004:4395", "telegram:7674283004:4396"]


def test_citation_strips_empty_marker() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[]§")

    assert clean == "答复正文"
    assert ids == []


@pytest.mark.parametrize("terminator", ["§", ""])
def test_citation_keeps_body_text_when_marker_not_at_end(terminator: str) -> None:
    text = (
        f"正文里提到 §cited:[mem_1]{terminator} 这串文本，但不是协议行。\n后面还有内容"
    )

    clean, ids = extract_cited_ids(text)

    assert clean == text
    assert ids == []


@pytest.mark.parametrize("terminator", ["§", ""])
def test_citation_extracts_before_trailing_protocol_tag(terminator: str) -> None:
    clean, ids = extract_cited_ids(f"答复正文\n§cited:[mem_1]{terminator} <meme:shy>")

    assert clean == "答复正文 <meme:shy>"
    assert ids == ["mem_1"]


@pytest.mark.parametrize("terminator", ["§", ""])
def test_citation_keeps_multiple_trailing_protocol_tags(terminator: str) -> None:
    clean, ids = extract_cited_ids(
        f"答复正文\n§cited:[mem_1]{terminator} <meme:shy> <foo:bar>"
    )

    assert clean == "答复正文 <meme:shy> <foo:bar>"
    assert ids == ["mem_1"]


def test_citation_rejects_marker_with_trailing_body_text() -> None:
    text = "答复正文\n§cited:[mem_1]§ 其他文字"

    clean, ids = extract_cited_ids(text)

    assert clean == text
    assert ids == []


def test_citation_rejects_malformed_trailing_protocol_tag() -> None:
    text = "答复正文\n§cited:[mem_1]§ <bad tag>"

    clean, ids = extract_cited_ids(text)

    assert clean == text
    assert ids == []


def test_citation_strips_leftover_trailing_protocol_tags() -> None:
    clean = strip_trailing_protocol_tags("答复正文 <memem:clever> <foo:bar>")

    assert clean == "答复正文"


def test_citation_keeps_body_when_leftover_tag_is_not_trailing() -> None:
    text = "答复正文 <memem:clever> 后面还有内容"

    assert strip_trailing_protocol_tags(text) == text


def test_citation_strips_inline_memory_refs() -> None:
    text = "第一段。 [§d0e3e6cf128a][§5557c1e640ce]\n第二段 [§mem_1]"

    assert strip_inline_memory_refs(text) == "第一段。\n第二段"


def test_citation_keeps_cited_protocol_text_in_body() -> None:
    text = "我们讨论过 §cited 标签协议，但这不是内联记忆 id。"

    assert strip_inline_memory_refs(text) == text


def test_citation_tool_chain_fallback_uses_recall_memory_cited_item_ids() -> None:
    tool_chain = [
        {
            "text": "thinking",
            "calls": [
                {
                    "name": "recall_memory",
                    "result": json.dumps(
                        {"count": 2, "cited_item_ids": ["mem_1", "mem_2"]}
                    ),
                }
            ],
        }
    ]

    assert extract_cited_ids_from_tool_chain(tool_chain) == ["mem_1", "mem_2"]


def test_citation_tool_chain_fallback_uses_item_ids() -> None:
    tool_chain = [
        {
            "text": "thinking",
            "calls": [
                {
                    "name": "recall_memory",
                    "result": json.dumps(
                        {"count": 2, "items": [{"id": "mem_1"}, {"id": "mem_2"}]}
                    ),
                }
            ],
        }
    ]

    assert extract_cited_ids_from_tool_chain(tool_chain) == ["mem_1", "mem_2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "expected_reply", "expected_ids"),
    [
        ("答复正文\n§cited:[mem_1]§", "答复正文", ["mem_1"]),
        (
            "答复正文\n§cited:[9b615a9c5f29,7e190efce6ff]",
            "答复正文",
            ["9b615a9c5f29", "7e190efce6ff"],
        ),
        (
            "答复正文\n§cited:[9b615a9c5f29,7e190efce6ff] <meme:shy>",
            "答复正文 <meme:shy>",
            ["9b615a9c5f29", "7e190efce6ff"],
        ),
        ("答复正文", "答复正文", ["mem_1"]),
    ],
)
async def test_citation_after_reasoning_writes_persist_slot(
    reply: str, expected_reply: str, expected_ids: list[str]
) -> None:
    module = CitationAfterReasoningModule()
    ctx = AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text=reply),
        streamed=False,
        tool_chain=(
            {
                "calls": [
                    {
                        "name": "recall_memory",
                        "result": json.dumps({"cited_item_ids": ["mem_1"]}),
                    }
                ]
            },
        ),
        context_retry={},
        reply=reply,
    )
    frame = FakeFrame(slots={"reasoning:ctx": ctx})

    await module.run(frame)

    assert ctx.reply == expected_reply
    assert frame.slots["persist:assistant:cited_memory_ids"] == expected_ids


@pytest.mark.asyncio
async def test_citation_after_reasoning_strips_inline_memory_refs() -> None:
    module = CitationAfterReasoningModule()
    ctx = AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(
            raw_text="答复正文 [§mem_1]\n§cited:[mem_1]§"
        ),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="答复正文 [§mem_1]\n§cited:[mem_1]§",
    )
    frame = FakeFrame(slots={"reasoning:ctx": ctx})

    await module.run(frame)

    assert ctx.reply == "答复正文"
    assert frame.slots["persist:assistant:cited_memory_ids"] == ["mem_1"]


@pytest.mark.asyncio
async def test_citation_cleanup_module_strips_leftover_protocol_tags() -> None:
    module = ProtocolTagCleanupModule()
    ctx = AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="答复正文 <memem:clever>"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="答复正文 <memem:clever>",
    )
    frame = FakeFrame(slots={"reasoning:ctx": ctx})

    await module.run(frame)

    assert ctx.reply == "答复正文"


async def test_setup_registers_modules(sdk_context: FakePluginContext) -> None:
    await setup(sdk_context)
    assert [
        type(module).__name__
        for module in sdk_context.lifecycle.modules["after_reasoning"]
    ] == ["CitationAfterReasoningModule", "ProtocolTagCleanupModule"]


@pytest.mark.parametrize(
    "module", [CitationAfterReasoningModule(), ProtocolTagCleanupModule()]
)
@pytest.mark.parametrize("slots", [{}, {"reasoning:ctx": "not a ctx"}])
async def test_modules_reject_a_missing_or_mistyped_reasoning_ctx(
    module: CitationAfterReasoningModule | ProtocolTagCleanupModule,
    slots: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match="reasoning:ctx must hold AfterReasoningCtx"):
        await module.run(FakeFrame(slots=slots))
