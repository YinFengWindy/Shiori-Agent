"""QQ-owned tool for reading only the host's current-turn text attachments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shiori_sdk.tools import (
    TOOL_ATTACHMENT_SCOPE_KEY,
    Tool,
    ToolAttachmentScope,
    ToolResult,
    ToolsCapability,
)

from .channel.files import MAX_FILE_BYTES, TEXT_FILE_SUFFIXES, validate_text

_CHARACTERS_PER_PAGE = 2000


class ReadAttachmentTool(Tool):
    """Expose QQ attachments without granting general filesystem access."""

    name = "read_attachment"
    description = (
        "读取当前 QQ 消息及其引用消息中的 txt/md 附件。只能使用本回合附件路径，"
        "不能读取其他消息或本地文件。默认按行读取，offset 为跳过的行数，limit 默认为 50。"
        "若文本包含超长行，自动按字符分页；按结果中的 character_offset 继续读取。"
    )
    context_precedence = frozenset({TOOL_ATTACHMENT_SCOPE_KEY})
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "本回合附件中列出的路径"},
            "offset": {
                "type": "integer",
                "minimum": 0,
                "description": "跳过的行数（0-based），默认 0",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 400,
                "description": "按行读取的最多行数，默认 50，输出受 10KB 上限保护",
            },
            "character_offset": {
                "type": "integer",
                "minimum": 0,
                "description": "按字符分页的起点（0-based），每页最多 2000 字符；不与 offset/limit 同用",
            },
        },
        "required": ["path"],
    }

    def __init__(self, tools: ToolsCapability) -> None:
        self._tools = tools

    async def execute(
        self,
        path: str,
        *,
        attachment_scope: ToolAttachmentScope | None = None,
        offset: int = 0,
        limit: int = 50,
        character_offset: int | None = None,
        **kwargs: Any,
    ) -> str | ToolResult:
        """Check authority before delegating ordinary line pages to read_file."""
        if not isinstance(attachment_scope, ToolAttachmentScope) or (
            attachment_scope.channel != "qq"
        ):
            return "错误：只能读取当前 QQ 回合的附件。"
        try:
            target = Path(path).resolve()
            allowed = {Path(item).resolve() for item in attachment_scope.paths}
            if target not in allowed:
                return "错误：该文件不属于当前 QQ 回合的附件。"
            if target.suffix.lower() not in TEXT_FILE_SUFFIXES:
                return "错误：附件读取仅支持 txt/md。"
            if offset < 0 or not 1 <= limit <= 400:
                return "错误：offset 必须非负，limit 必须在 1 到 400 之间。"
            if character_offset is not None and (
                character_offset < 0 or offset != 0 or limit != 50
            ):
                return "错误：character_offset 必须非负，且不能与 offset/limit 同用。"
            with target.open("rb") as file:
                data = file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                return "错误：附件超过 2 MiB 上限。"
            text = validate_text(data)
        except (OSError, ValueError) as exc:
            return f"错误：附件无法读取：{exc}"

        # read_file deliberately declines a >10KB single line and recommends
        # shell. QQ group members have no shell, so such text has character pages.
        if character_offset is not None or any(
            len(line) > 8000 for line in data.splitlines()
        ):
            if offset:
                return "错误：此文件含超长行，请使用 character_offset 按字符分页。"
            start = character_offset or 0
            end = min(start + _CHARACTERS_PER_PAGE, len(text))
            continuation = (
                f"继续读取请传 character_offset={end}"
                if end < len(text)
                else "已读到文件末尾"
            )
            return (
                f"{text[start:end]}\n\n"
                f"[字符 {start}–{end} / 共 {len(text)} 字符；{continuation}]"
            )
        reader = self._tools.get_tool("read_file")
        if reader is None:
            return "错误：文本读取器当前不可用。"
        return await reader.execute(path=str(target), offset=offset, limit=limit)
