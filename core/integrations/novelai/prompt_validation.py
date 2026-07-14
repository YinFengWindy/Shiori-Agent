from __future__ import annotations


def validate_novelai_prompt(prompt: str, *, field_name: str) -> None:
    """Require NovelAI prompts to contain ASCII-compatible English tags only."""

    if not prompt.isascii():
        raise ValueError(
            f"{field_name} 仅支持英文 NovelAI tags，请先将中文描述转换为英文 tags"
        )
