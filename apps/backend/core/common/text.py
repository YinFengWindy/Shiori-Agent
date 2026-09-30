"""提示词与预览共用的文本工具。"""

from __future__ import annotations


def truncate_text(text: str, limit: int) -> str:
    """``text`` 超过 ``limit`` 字时截断，并在末尾注明截掉的字数。"""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"…（截断 {len(text) - limit} 字）"
