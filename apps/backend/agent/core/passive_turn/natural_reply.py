"""Validate model-authored chat messages before any user-visible delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from agent.provider import LLMProvider, LLMResponse, is_truncated_finish_reason
from agent.tool_runtime import append_assistant_tool_calls, append_tool_result
from agent.turns.reply_sequence import ReplySequence, ReplySequencePolicy
from prompts.natural_chat import FINISH_REPLY_TOOL_NAME
from .budgeted_request import budgeted_chat
from .reply_recovery import CompletedReply


class InvalidNaturalReply(ValueError):
    """A natural-chat turn has no validated, deliverable message list."""


@dataclass(frozen=True)
class NaturalReply:
    """Validated messages and their original completion-tool arguments."""

    sequence: ReplySequence
    raw_text: str
    policy: ReplySequencePolicy

    @property
    def decorated_input(self) -> str:
        """Carry boundaries through the existing once-per-turn decorators.

        This opaque boundary is created by the host, never requested from the
        model. Literal protocol examples and unclosed code fences in individual
        messages therefore cannot change the model's chosen message boundaries.
        """
        return f"\n{self.policy.separator}\n".join(self.sequence.messages)


def finish_reply_schema(*, strict: bool = False) -> dict[str, Any]:
    """Describe a final answer, without granting any external sending ability."""
    return {
        "type": "function",
        "function": {
            "name": FINISH_REPLY_TOOL_NAME,
            "description": (
                "完成本轮对话回复。messages 每项是一条独立聊天消息，"
                "内容、条数和分条位置由你决定，一条足够时只放一项。"
                "需要业务工具时先使用工具，获得结果后单独调用本工具。"
                "本工具只提交回复，由系统负责发送；不要在普通正文中另发回复。"
            ),
            **({"strict": True} if strict else {}),
            "parameters": {
                "type": "object",
                "properties": {
                    "messages": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["messages"],
                "additionalProperties": False,
            },
        },
    }


def _validate(response: LLMResponse) -> NaturalReply:
    if response.refused or is_truncated_finish_reason(response.finish_reason):
        raise InvalidNaturalReply("回复被拒绝或截断，尚未形成完整消息列表")
    if len(response.tool_calls) != 1:
        raise InvalidNaturalReply("请单独调用 finish_reply 完成本轮回复")
    call = response.tool_calls[0]
    if call.name != FINISH_REPLY_TOOL_NAME:
        raise InvalidNaturalReply("格式纠正只能调用 finish_reply，不能执行业务工具")
    if call.arguments_error:
        raise InvalidNaturalReply("finish_reply 的参数必须是有效 JSON 对象")
    payload = call.arguments
    if not isinstance(payload, dict) or set(payload) != {"messages"}:
        raise InvalidNaturalReply("finish_reply 只能包含 messages 字段")
    messages = payload["messages"]
    if not isinstance(messages, list) or not messages:
        raise InvalidNaturalReply("messages 必须是非空消息列表")
    if any(not isinstance(item, str) or not item.strip() for item in messages):
        raise InvalidNaturalReply("messages 每项必须是非空字符串")
    separator = f"<shiori-message-{uuid4().hex}/>"
    while any(separator in item for item in messages):
        separator = f"<shiori-message-{uuid4().hex}/>"
    return NaturalReply(
        sequence=ReplySequence(tuple(messages)),
        raw_text=call.raw_arguments or json.dumps(payload, ensure_ascii=False),
        policy=ReplySequencePolicy(separator, message_count=len(messages)),
    )


class NaturalReplyProtocol:
    """Own one bounded format correction, independent of business-tool execution."""

    def __init__(self) -> None:
        self.reply: NaturalReply | None = None
        self.corrected = False

    def schemas(self, tools: list[dict]) -> list[dict]:
        """Keep the reply capability visible even after tool discovery/compaction."""
        reply_tool = finish_reply_schema()
        if any(
            tool["function"]["name"] == FINISH_REPLY_TOOL_NAME and tool != reply_tool
            for tool in tools
        ):
            raise ValueError("finish_reply 是自然聊天保留的完成回复工具")
        return [
            tool for tool in tools if tool["function"]["name"] != FINISH_REPLY_TOOL_NAME
        ] + [reply_tool]

    def pending_work(self, response: LLMResponse) -> bool:
        """Ignore premature reply drafts until the requested work has completed."""
        work = [
            call for call in response.tool_calls if call.name != FINISH_REPLY_TOOL_NAME
        ]
        if not work:
            return False
        for call in work:
            if call.arguments_error:
                raise ValueError(f"工具 {call.name} 的参数不是有效 JSON 对象")
        # A finish call in the same batch cannot incorporate these tool results.
        # It is not sent or executed; the normal loop continues after the work.
        response.tool_calls = work
        return True

    async def complete(
        self,
        response: LLMResponse,
        *,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
        max_tokens: int,
    ) -> CompletedReply:
        """Accept a valid list, or correct only the final format once."""
        calls = (response,)
        try:
            reply = _validate(response)
        except InvalidNaturalReply as exc:
            if self.corrected or response.refused:
                raise
            self.corrected = True
            correction = list(messages)
            if response.tool_calls:
                append_assistant_tool_calls(
                    correction,
                    content=response.content,
                    tool_calls=response.tool_calls,
                    provider_fields=response.provider_fields,
                )
                for call in response.tool_calls:
                    append_tool_result(
                        correction,
                        tool_call_id=call.id,
                        tool_name=call.name,
                        content=f"回复未发送：{exc}",
                    )
            elif response.content:
                correction.append({"role": "assistant", "content": response.content})
            correction.append(
                {
                    "role": "user",
                    "content": (
                        f"[回复格式纠正] {exc}。刚才的回复尚未发送。"
                        "请基于已有结果通过 finish_reply 提交 messages 列表，"
                        "保留原本要说的意思，自行决定消息边界。"
                        "不要执行业务工具，不要解释发送格式。"
                    ),
                }
            )
            strict = (
                isinstance(provider, LLMProvider) and provider.supports_strict_tools
            )
            tool = finish_reply_schema(strict=strict)
            corrected = await budgeted_chat(
                provider,
                messages=correction,
                tools=[tool],
                reply_tool=tool,
                tool_choice={
                    "type": "function",
                    "function": {"name": FINISH_REPLY_TOOL_NAME},
                },
                model=model,
                max_tokens=max_tokens,
                # DeepSeek thinking does not support forcing a named tool.
                # Only this format correction is auxiliary; original thinking
                # and the role's normal reasoning configuration stay intact.
                call_purpose="auxiliary",
                defer_tool_argument_errors=True,
            )
            reply = _validate(corrected)
            calls = (response, corrected)
            corrected.thinking = response.thinking or corrected.thinking
            response = corrected
        self.reply = reply
        return CompletedReply(
            response=replace(response, content=reply.sequence.content, tool_calls=[]),
            calls=calls,
        )
