from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from plugins.qq.backend.read_attachment import ReadAttachmentTool
from shiori_sdk.testing.tools import FakeTools
from shiori_sdk.tools import Tool, ToolAttachmentScope, normalize_tool_result


class _Reader(Tool):
    name = "read_file"
    description = "Records the public delegation boundary."
    parameters = {"type": "object"}

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        return "读取结果"


def _tool():
    tools, reader = FakeTools(), _Reader()
    tools.register(reader)
    return ReadAttachmentTool(tools), reader


@pytest.mark.asyncio
async def test_authorized_attachment_delegates_only_path_and_line_page(tmp_path: Path):
    path = tmp_path / "故事.md"
    path.write_text("正文\n续文", encoding="utf-8")
    tool, reader = _tool()
    result = await tool.execute(
        str(path),
        attachment_scope=ToolAttachmentScope("qq", (str(path),)),
        offset=1,
        limit=25,
        allowed_dir=str(tmp_path),
        channel="desktop",
    )
    assert result == "读取结果"
    assert reader.calls == [{"path": str(path.resolve()), "offset": 1, "limit": 25}]


@pytest.mark.asyncio
async def test_other_turn_chat_channel_and_forged_scope_cannot_read(tmp_path: Path):
    path = tmp_path / "private.txt"
    path.write_text("不应读取", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("其他回合", encoding="utf-8")
    tool, reader = _tool()
    scopes: list[Any] = [
        None,
        ToolAttachmentScope("qq", (str(other),)),
        ToolAttachmentScope("desktop", (str(path),)),
        {"channel": "qq", "paths": [str(path)]},
    ]
    for scope in scopes:
        result = normalize_tool_result(
            await tool.execute(str(path), attachment_scope=scope)
        )
        assert "错误" in result.text
    assert reader.calls == []


@pytest.mark.asyncio
async def test_concurrent_turns_have_no_shared_or_inherited_allowlist(tmp_path: Path):
    tool, reader = _tool()
    paths = [tmp_path / "a.txt", tmp_path / "b.txt"]
    for path in paths:
        path.write_text(path.name, encoding="utf-8")
    results = await asyncio.gather(
        *(
            tool.execute(
                str(path), attachment_scope=ToolAttachmentScope("qq", (str(path),))
            )
            for path in paths
        )
    )
    assert results == ["读取结果", "读取结果"]
    assert "错误" in normalize_tool_result(await tool.execute(str(paths[0]))).text
    assert len(reader.calls) == 2


@pytest.mark.asyncio
async def test_disguised_binary_and_nontext_extension_never_reach_reader(
    tmp_path: Path,
):
    tool, reader = _tool()
    for name, content in (("fake.txt", b"\x00binary"), ("fake.png", b"plaintext")):
        path = tmp_path / name
        path.write_bytes(content)
        result = await tool.execute(
            str(path),
            attachment_scope=ToolAttachmentScope("qq", (str(path),)),
        )
        assert "错误" in normalize_tool_result(result).text
    assert reader.calls == []


@pytest.mark.asyncio
async def test_long_single_line_has_real_character_pages_without_shell(tmp_path: Path):
    path = tmp_path / "长文章.txt"
    content = "正文" * 5000
    path.write_text(content, encoding="utf-8")
    tool, reader = _tool()
    scope = ToolAttachmentScope("qq", (str(path),))
    result = await tool.execute(str(path), attachment_scope=scope)
    assert isinstance(result, str)
    assert result.startswith(content[:2000])
    assert "character_offset=2000" in result and "shell" not in result
    last = await tool.execute(str(path), attachment_scope=scope, character_offset=8000)
    assert isinstance(last, str)
    assert last.startswith(content[8000:]) and "已读到文件末尾" in last
    assert reader.calls == []
