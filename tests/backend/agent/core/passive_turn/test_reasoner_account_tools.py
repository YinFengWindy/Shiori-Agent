"""The real turn uses account grants for execution without importing private context."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock

from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.turns.reply_interruption import ReplyInterruption, reply_interruption_scope

import pytest

from agent.lifecycle.plugin_contributions import StaticPluginContributions
from agent.provider import LLMResponse, ToolCall
from agent.tool_hooks.base import ToolHook, HookOutcome
from agent.tool_hooks.types import HookContext
from agent.tools.external_access import ExternalArgumentLimit
from agent.tools.tool_search import ToolSearchTool
from core.channels.hub import ChannelHub
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.conversation import AccountConversation
from shiori_sdk.channels.message_source import MessageSource
from shiori_sdk.messages import InboundMessage
from shiori_sdk.tools import Tool
from tests.support.external_turns import ExternalTurnHost, SECRETS, request_text


class Retarget(ToolHook):
    name = "test:retarget"
    event = "pre_tool_use"

    def matches(self, ctx: HookContext) -> bool:
        return ctx.request.tool_name == "public"

    async def run(self, ctx: HookContext) -> HookOutcome:
        return HookOutcome(updated_input={"mode": "all"})


@pytest.mark.parametrize(
    "granted,disabled,interrupted",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
    ],
)
async def test_account_rule_controls_search_dynamic_mcp_and_post_hook_execution(
    tmp_path, granted, disabled, interrupted
):
    host = ExternalTurnHost(tmp_path)
    if interrupted:
        host.roles.update_role("mira", runtime_config={"natural_chat_enabled": True})
    accounts = host.roles.accounts
    row = accounts.register(
        plugin_id="grok_bot",
        platform="grok_bot",
        platform_account_id="one",
        config_ref="one",
        token="live",
        role_id="mira",
        response_rules=AccountResponseRules(allow_full_tools=granted),
    )
    accounts.set_rules_handler("grok_bot", lambda *_: None)
    accounts.report(
        row.record.id,
        "live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountConversation("grok_bot_one", "dm:peer"),
    )
    tools = host.loop.tools
    tools.bind_accounts(accounts)
    tools.register(ToolSearchTool(tools), always_on=True, external_allowed=True)
    calls = []
    interruption = ReplyInterruption() if interrupted else None

    class Dynamic(Tool):
        name = "mcp_dynamic"
        description = "A newly connected MCP tool"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            calls.append("mcp")
            return "mcp done"

    class Private(Tool):
        name = "user_only"
        description = "A private tool"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            calls.append("private")
            return "private done"

    class Limited(Tool):
        name = "public"
        description = "A tool whose external mode is limited"
        parameters = {"type": "object", "properties": {"mode": {"type": "string"}}}

        async def execute(self, **kwargs):
            calls.append(kwargs["mode"])
            if interruption is not None:
                # A supplement invalidates a tool already executing under its
                # admitted grant. Finish this effect, then recheck the next turn.
                interruption.invalidate()
                accounts.set_response_rules(row.record.id, AccountResponseRules())
            tools.register(Dynamic(), source_type="mcp", source_name="fixture")
            return "registered"

    tools.register(Private())
    tools.register(
        Limited(),
        always_on=True,
        external_allowed=True,
        external_limit=ExternalArgumentLimit(
            "mode", frozenset({"public"}), "limited", "public only"
        ),
    )
    host.loop.bind_plugin_contributions(
        StaticPluginContributions(tool_hooks=[Retarget()])
    )
    original_chat = host.provider.chat
    responses = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall("s1", "tool_search", {"query": "select:user_only"}),
                ToolCall("limited", "public", {"mode": "public"}),
                ToolCall("private", "user_only", {}),
            ],
        ),
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall("s2", "tool_search", {"query": "select:mcp_dynamic"}),
                ToolCall("mcp", "mcp_dynamic", {}),
            ],
        ),
        LLMResponse(content="完成", tool_calls=[]),
    ]

    async def chat(**kwargs):
        if kwargs.get("response_format"):
            return await original_chat(**kwargs)
        host.provider.requests.append(kwargs)
        return responses.pop(0)

    host.provider.chat = AsyncMock(side_effect=chat)
    hub = ChannelHub.from_workspace(
        tmp_path, session_manager=host.manager, role_store=host.roles
    )
    incoming = InboundMessage(
        channel="grok_bot_one",
        chat_id="dm:peer",
        sender="peer",
        content="请使用工具",
        metadata={
            "account_id": row.record.id,
            "chat_type": "private",
            "account_full_tools": True,
            "sender_is_user": True,
            "disabled_tools": ["user_only"] if disabled else [],
        },
    )
    routed = hub.route_account_inbound(incoming)
    assert routed is not None
    assert not MessageSource.from_inbound(routed).sender_is_user
    with (
        ChannelSequenceOwner().bind(host.loop.bus) if interrupted else nullcontext()
    ), reply_interruption_scope(interruption), (
        pytest.raises(asyncio.CancelledError) if interrupted else nullcontext()
    ):
        await host.loop._process_role_scoped(
            routed, routed.session_key, dispatch_outbound=False
        )
    if interrupted:
        assert len(host.provider.requests) == 1
        messages = host.manager.get_or_create("role:mira").messages
        assert any(message["content"] == "请使用工具" for message in messages)
        assert "registered" in str(messages)
        assert "private done" not in str(messages)
        responses.clear()
    expected_calls = (
        ["all"]
        if interrupted
        else (
            (["all", "mcp"] if disabled else ["all", "private", "mcp"])
            if granted
            else []
        )
    )
    assert calls == expected_calls
    assert all(
        secret not in request_text(request)
        for secret in SECRETS
        for request in host.provider.requests
    )
    first_schema = next(
        s
        for s in host.provider.requests[0]["tools"]
        if s["function"]["name"] == "public"
    )
    assert (
        "enum" in first_schema["function"]["parameters"]["properties"]["mode"]
    ) is not granted
    assert host.loop.tools.get_context().get("sender_is_user") == "false"
    if granted:
        accounts.set_response_rules(row.record.id, AccountResponseRules())
        assert not tools.allows_full_tools(
            routed
        ), "a queued old grant cannot survive revocation"
        responses.extend(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall("revoked", "user_only", {}),
                        ToolCall("revoked-mcp", "mcp_dynamic", {}),
                    ],
                ),
                LLMResponse(content="不能执行", tool_calls=[]),
            ]
        )
        await host.loop._process_role_scoped(
            routed, routed.session_key, dispatch_outbound=False
        )
        assert calls == expected_calls
        if interrupted:
            assert "registered" in request_text(host.provider.requests[1])
