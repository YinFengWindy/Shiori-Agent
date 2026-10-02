"""Shared command parsing and before-turn replies for command contributions."""

from agent.lifecycle.types import BeforeTurnCtx, TurnState


def abort_command(state: TurnState, reply: str) -> BeforeTurnCtx:
    """Reply to a handled command without retrieval, history, or LLM execution."""
    return BeforeTurnCtx(
        session_key=state.session_key,
        channel=state.msg.channel,
        chat_id=state.msg.chat_id,
        content=state.msg.content,
        timestamp=state.msg.timestamp,
        skill_names=[],
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=state.context_scope,
        abort=True,
        abort_reply=reply,
    )
