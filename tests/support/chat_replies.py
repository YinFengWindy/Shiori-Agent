"""Script visible chat messages using the reply contract advertised by a request."""

from agent.provider import LLMResponse, ToolCall
from prompts.natural_chat import FINISH_REPLY_TOOL_NAME


def chat_reply(
    messages: list[str], *, tools: list[dict], plain_content: str | None = None
) -> LLMResponse:
    """Emulate a compliant model without changing interruption test expectations."""
    if any(tool["function"]["name"] == FINISH_REPLY_TOOL_NAME for tool in tools):
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall("reply", FINISH_REPLY_TOOL_NAME, {"messages": messages})
            ],
        )
    return LLMResponse(
        content=plain_content if plain_content is not None else "\n\n".join(messages)
    )
