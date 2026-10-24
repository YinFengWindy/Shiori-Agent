"""The early turn result of an answered command."""

from datetime import datetime


from agent.lifecycle.commands import abort_command
from agent.lifecycle.types import TurnState
from shiori_sdk.messages import InboundMessage


def test_abort_command_preserves_routing_and_skips_conversation_work():
    timestamp = datetime(2026, 9, 11, 12)
    state = TurnState(
        msg=InboundMessage(
            channel="telegram",
            sender="42",
            chat_id="chat-42",
            content="/UNDO@ShioriBot",
            timestamp=timestamp,
        ),
        session_key="telegram:chat-42",
        dispatch_outbound=True,
    )

    ctx = abort_command(state, "已撤销上一轮对话。")

    assert ctx.abort is True
    assert ctx.abort_reply == "已撤销上一轮对话。"
    assert (ctx.session_key, ctx.channel, ctx.chat_id) == (
        state.session_key,
        "telegram",
        "chat-42",
    )
    assert (ctx.content, ctx.timestamp) == (state.msg.content, timestamp)
    assert ctx.history_messages == ()
    assert ctx.retrieved_memory_block == ""
    assert ctx.retrieval_trace_raw is None
    assert ctx.skill_names == []
