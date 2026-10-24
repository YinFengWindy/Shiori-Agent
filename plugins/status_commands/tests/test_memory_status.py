"""Session consolidation status without observe or a storage query."""

import pytest

from .conftest import Session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", ["/memorystatus", "/MEMORY_STATUS@Bot ignored", " /compact_status "]
)
async def test_memory_aliases_keep_real_user_counts_and_last_preview(plugin, command):
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
    assert await plugin.answer(command, session) == (
        "🧠 记忆整理状态：\n上次整理到 1 条用户消息之前。\n\n"
        "最后已整理的用户消息：\n“第一条”\n\n"
        "尚未整理的用户消息数：1\n当前会话消息数：4"
    )
    assert session.last_consolidated == 3
    assert len(session.messages) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("last", "expected"),
    [
        (-9, "当前会话还没有完成过记忆整理。"),
        (99, "当前会话已经整理到最新的用户消息。"),
    ],
)
async def test_memory_position_is_clamped_without_changing_session(
    plugin, last, expected
):
    session = Session(
        key="telegram:1",
        messages=[{"role": "user", "content": "hi"}],
        last_consolidated=last,
    )
    reply = await plugin.answer("/memorystatus", session)
    assert reply is not None and expected in reply
    assert session.last_consolidated == last
