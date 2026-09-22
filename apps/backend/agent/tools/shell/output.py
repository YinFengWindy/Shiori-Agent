"""Shell 命令输出序列化与截断。"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .constants import _MAX_OUTPUT, _STREAM_CHUNK_SIZE


async def _read_output(stream: asyncio.StreamReader | None):
    """逐流增量解码 UTF-8，避免读取块边界拆断中文字符。"""
    if stream is None:
        return
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        data = await stream.read(_STREAM_CHUNK_SIZE)
        text = decoder.decode(data, final=not data)
        if text:
            yield text
        if not data:
            break


def _err(msg: str) -> str:
    return json.dumps({"error": msg}, ensure_ascii=False)


def _truncate(content: str) -> dict[str, Any]:
    """超过阈值时优先保留尾部，便于看到命令结果与错误摘要。"""
    if len(content) <= _MAX_OUTPUT:
        return {
            "text": content,
            "truncated": False,
            "strategy": "tail",
            "full_length": len(content),
            "returned_length": len(content),
            "omitted_lines": 0,
        }

    omitted = content[: len(content) - _MAX_OUTPUT]
    omitted_lines = omitted.count("\n")
    prefix = f"... [{omitted_lines} 行已省略] ...\n\n"
    tail_budget = max(0, _MAX_OUTPUT - len(prefix))
    tail = content[-tail_budget:] if tail_budget > 0 else ""
    text = prefix + tail
    return {
        "text": text,
        "truncated": True,
        "strategy": "tail",
        "full_length": len(content),
        "returned_length": len(text),
        "omitted_lines": omitted_lines,
    }


def _write_full_output(content: str) -> str:
    fd, path = tempfile.mkstemp(prefix="shiori-shell-", suffix=".log")
    os.close(fd)
    Path(path).write_text(content, encoding="utf-8")
    return path
