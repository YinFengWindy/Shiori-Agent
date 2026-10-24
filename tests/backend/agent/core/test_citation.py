"""Reading and cleaning memory citations in replies (D9).

Moved from the deleted citation plugin's tests (P3-4, #902): the marker
grammar, the recall_memory fallback and the leftover-marker cleanup.
"""

from __future__ import annotations

import json

import pytest

from agent.core.citation import (
    cited_ids_from_tool_chain,
    extract_cited_ids,
    strip_inline_memory_refs,
    strip_trailing_protocol_tags,
    take_citations,
)


@pytest.mark.parametrize(
    ("text", "clean", "ids"),
    [
        ("答复正文\n§cited:[mem_1,mem-2]§", "答复正文", ["mem_1", "mem-2"]),
        # The model may omit the final §.
        ("§cited:[9b615a9c5f29,7e190efce6ff]", "", ["9b615a9c5f29", "7e190efce6ff"]),
        ("答复正文\n§cited:[mem_1, mem-2]§", "答复正文", ["mem_1", "mem-2"]),
        (
            "答复正文\n§cited:[telegram:7674283004:4395,telegram:7674283004:4396]§",
            "答复正文",
            ["telegram:7674283004:4395", "telegram:7674283004:4396"],
        ),
        ("答复正文\n§cited:[]§", "答复正文", []),
        # Protocol tags after the marker stay for the plugins.
        ("答复正文\n§cited:[mem_1]§ <meme:shy>", "答复正文 <meme:shy>", ["mem_1"]),
        ("答复正文\n§cited:[mem_1] <meme:shy>", "答复正文 <meme:shy>", ["mem_1"]),
        (
            "答复正文\n§cited:[mem_1]§ <meme:shy> <foo:bar>",
            "答复正文 <meme:shy> <foo:bar>",
            ["mem_1"],
        ),
    ],
)
def test_a_trailing_marker_is_removed_and_its_ids_read(
    text: str, clean: str, ids: list[str]
) -> None:
    assert extract_cited_ids(text) == (clean, ids)


@pytest.mark.parametrize(
    "text",
    [
        "正文里提到 §cited:[mem_1]§ 这串文本，但不是协议行。\n后面还有内容",
        "正文里提到 §cited:[mem_1] 这串文本，但不是协议行。\n后面还有内容",
        "答复正文\n§cited:[mem_1]§ 其他文字",
        "答复正文\n§cited:[mem_1]§ <bad tag>",
    ],
)
def test_a_marker_not_at_the_end_is_body_text(text: str) -> None:
    assert extract_cited_ids(text) == (text, [])


def test_only_trailing_protocol_tags_are_leftovers() -> None:
    assert (
        strip_trailing_protocol_tags("答复正文 <memem:clever> <foo:bar>") == "答复正文"
    )
    kept = "答复正文 <memem:clever> 后面还有内容"
    assert strip_trailing_protocol_tags(kept) == kept


def test_inline_memory_refs_are_removed_but_cited_prose_kept() -> None:
    text = "第一段。 [§d0e3e6cf128a][§5557c1e640ce]\n第二段 [§mem_1]"
    assert strip_inline_memory_refs(text) == "第一段。\n第二段"
    prose = "我们讨论过 §cited 标签协议，但这不是内联记忆 id。"
    assert strip_inline_memory_refs(prose) == prose


def _recall(result: dict[str, object]) -> dict[str, object]:
    return {"calls": [{"name": "recall_memory", "result": json.dumps(result)}]}


@pytest.mark.parametrize(
    "result",
    [
        {"count": 2, "cited_item_ids": ["mem_1", "mem_2"]},
        {"count": 2, "items": [{"id": "mem_1"}, {"id": "mem_2"}]},
    ],
)
def test_recall_results_supply_the_ids(result: dict[str, object]) -> None:
    assert cited_ids_from_tool_chain([_recall(result)]) == ["mem_1", "mem_2"]


@pytest.mark.parametrize(
    ("messages", "cleaned", "ids"),
    [
        (("答复正文 [§mem_9]\n§cited:[mem_1]§",), ("答复正文",), ["mem_1"]),
        # No marker in any message: the recall results stand in.
        (("答复正文",), ("答复正文",), ["mem_r"]),
        (("早呀[§mem-2]", "加油 §cited:[mem-3]§"), ("早呀", "加油"), ["mem-3"]),
    ],
)
def test_take_citations_prefers_markers_over_recall_results(
    messages: tuple[str, ...], cleaned: tuple[str, ...], ids: list[str]
) -> None:
    chain = [_recall({"cited_item_ids": ["mem_r"]})]
    assert take_citations(messages, chain) == (cleaned, ids)
