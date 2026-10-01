from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.core.response_parser import ResponseMetadata
from agent.lifecycle.types import AfterReasoningCtx
from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_citation_plugin_module() -> Any:
    path = PLUGIN_DIR / "backend" / "plugin.py"
    spec = importlib.util.spec_from_file_location("test_citation_plugin", path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_citation_module = _load_citation_plugin_module()
CitationAfterReasoningModule = _citation_module.CitationAfterReasoningModule
ProtocolTagCleanupModule = _citation_module.ProtocolTagCleanupModule
extract_cited_ids = _citation_module.extract_cited_ids
extract_cited_ids_from_tool_chain = _citation_module.extract_cited_ids_from_tool_chain
strip_trailing_protocol_tags = _citation_module.strip_trailing_protocol_tags
strip_inline_memory_refs = _citation_module.strip_inline_memory_refs


def test_citation_extracts_ascii_marker_only_at_end() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[mem_1,mem-2]§")

    assert clean == "答复正文"
    assert ids == ["mem_1", "mem-2"]


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


def test_citation_keeps_body_text_when_marker_not_at_end() -> None:
    text = "正文里提到 §cited:[mem_1]§ 这串文本，但不是协议行。\n后面还有内容"

    clean, ids = extract_cited_ids(text)

    assert clean == text
    assert ids == []


def test_citation_extracts_before_trailing_protocol_tag() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[mem_1]§ <meme:shy>")

    assert clean == "答复正文 <meme:shy>"
    assert ids == ["mem_1"]


def test_citation_keeps_multiple_trailing_protocol_tags() -> None:
    clean, ids = extract_cited_ids("答复正文\n§cited:[mem_1]§ <meme:shy> <foo:bar>")

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
async def test_citation_setup_contributes_expected_phase_modules_via_kernel(
    tmp_path: Path,
) -> None:
    """setup(ctx) 只贡献回复后处理模块，不再向 prompt 注入引用要求。

    用真实 PluginKernel 装配真实插件目录来验证，而不是自造 fake capability——
    fake 与真实 capability 契约脱钩，capability 改坏也不会让测试变红（#182 评审）。
    """
    root = tmp_path / "plugins"
    root.mkdir()
    source = tmp_path / "source-citation"
    stage_plugin_package(PLUGIN_DIR, source)
    environment = source / ".venv/Lib/site-packages"
    environment.mkdir(parents=True)
    (environment / "review-marker.txt").write_text("environment", encoding="utf-8")
    stage_plugin_package(source, root / "citation")
    assert (root / "citation/backend/plugin.py").is_file()
    assert (root / "citation/manifest.yaml").is_file()
    assert not (root / "citation/.venv").exists()
    kernel = PluginKernel([root], services=HostServices(event_bus=EventBus()))
    await kernel.load_all()

    assert kernel.prompt_render_modules == []
    assert [type(m).__name__ for m in kernel.after_reasoning_modules] == [
        "CitationAfterReasoningModule",
        "ProtocolTagCleanupModule",
    ]

    # 卸载后贡献必须整体撤回，证明生命周期与 phase 槽位真正挂在插件作用域上
    _ = await kernel.unload("citation")
    assert kernel.prompt_render_modules == []
    assert kernel.after_reasoning_modules == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["答复正文\n§cited:[mem_1]§", "答复正文"])
async def test_citation_after_reasoning_writes_persist_slot(reply: str) -> None:
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
    frame = SimpleNamespace(slots={"reasoning:ctx": ctx})

    await module.run(frame)

    assert ctx.reply == "答复正文"
    assert frame.slots["persist:assistant:cited_memory_ids"] == ["mem_1"]


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
    frame = SimpleNamespace(slots={"reasoning:ctx": ctx})

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
    frame = SimpleNamespace(slots={"reasoning:ctx": ctx})

    await module.run(frame)

    assert ctx.reply == "答复正文"
