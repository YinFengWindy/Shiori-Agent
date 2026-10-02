from bus.events import InboundMessage, OutboundMessage
from agent.core.types import (
    ChatMessage,
    ContextBundle,
    LLMResponse,
    ReasonerResult,
    LLMToolCall as ToolCall,
    TurnRecord,
)


def test_agent_core_foundation_types_construct_cleanly():
    inbound = InboundMessage(
        channel="cli",
        sender="u",
        chat_id="1",
        content="hello",
    )
    outbound = OutboundMessage(
        channel="cli",
        chat_id="1",
        content="ok",
    )
    bundle = ContextBundle(history=[ChatMessage(role="user", content="hi")])
    response = LLMResponse(reply="done", tool_calls=[ToolCall(id="c1", name="dummy")])
    result = ReasonerResult(reply="done", invocations=response.tool_calls)
    record = TurnRecord(msg=inbound, reply="done", invocations=response.tool_calls)

    assert inbound.session_key == "cli:1"
    assert outbound.content == "ok"
    assert bundle.history[0].content == "hi"
    assert response.tool_calls[0].name == "dummy"
    assert result.invocations[0].id == "c1"
    assert record.reply == "done"
