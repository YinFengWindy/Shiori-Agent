"""Session consolidation status without observe or a storage query."""

import pytest

from .conftest import Session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", ["/memorystatus", "/MEMORY_STATUS@Bot ignored", " /compact_status "]
)
async def test_memory_aliases_keep_real_user_counts_and_last_preview(
    backend, command_frame, command
):
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
    frame = command_frame(command, session)
    await backend.MemoryStatusCommandModule().run(frame)
    assert frame.slots["session:ctx"].abort_reply == (
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
    backend, command_frame, last, expected
):
    session = Session(
        key="telegram:1",
        messages=[{"role": "user", "content": "hi"}],
        last_consolidated=last,
    )
    frame = command_frame("/memorystatus", session)
    await backend.MemoryStatusCommandModule().run(frame)
    assert expected in frame.slots["session:ctx"].abort_reply
    assert session.last_consolidated == last


@pytest.mark.asyncio
async def test_memory_command_preserves_prior_abort_and_ignores_unrelated_input(
    backend, command_frame
):
    module = backend.MemoryStatusCommandModule()
    frame = command_frame("/memorystatus")
    previous = object()
    frame.slots["session:ctx"] = previous
    await module.run(frame)
    assert frame.slots["session:ctx"] is previous
    frame = command_frame("hello")
    await module.run(frame)
    assert "session:ctx" not in frame.slots
