"""Session consolidation status without observe or a storage query."""

import pytest

from .conftest import Session


@pytest.mark.asyncio
async def test_memory_status_keeps_real_user_counts_and_last_preview(plugin):
    session = Session(
        key="telegram:1",
        last_consolidated=3,
        messages=[
            {"role": "user", "content": "[SYSTEM_CONTEXT_FRAME] hidden"},
            {"role": "user", "content": [{"type": "text", "text": "第一条"}]},
            {"role": "assistant", "content": "回复"},
            {"role": "user", "content": "第二条"},
        ],
    )
    assert await plugin.answer("/memorystatus", session) == (
        "🧠 记忆整理状态：\n上次整理到 1 条用户消息之前。\n\n"
        "最后已整理的用户消息：\n“第一条”\n\n"
        "尚未整理的用户消息数：1\n当前会话消息数：4"
    )
    assert session.last_consolidated == 3
    assert len(session.messages) == 4
