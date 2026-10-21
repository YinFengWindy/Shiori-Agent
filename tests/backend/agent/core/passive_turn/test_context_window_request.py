"""Idle tool schemas use the same current account grant as actual turns."""

from agent.core.passive_turn.context_window_request import (
    prepare_context_window_request,
)
from conversation.context_scope import turn_context_view
from core.channels.hub import ChannelHub
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.conversation import AccountConversation
from shiori_sdk.messages import InboundMessage
from tests.support.host_external_turns import ExternalTurnHost, SECRETS


async def test_idle_schema_rechecks_revoked_account_without_importing_user_history(
    tmp_path,
):
    host = ExternalTurnHost(tmp_path)
    accounts = host.roles.accounts
    row = accounts.register(
        plugin_id="grok_bot",
        platform="grok_bot",
        platform_account_id="one",
        config_ref="one",
        token="live",
        role_id="mira",
        response_rules=AccountResponseRules(allow_full_tools=True),
    )
    accounts.set_rules_handler("grok_bot", lambda *_: None)
    accounts.report(
        row.record.id,
        "live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountConversation("grok_bot_one", "dm:peer"),
    )
    host.loop.tools.bind_accounts(accounts)
    hub = ChannelHub.from_workspace(
        tmp_path, session_manager=host.manager, role_store=host.roles
    )
    message = hub.route_account_inbound(
        InboundMessage(
            channel="grok_bot_one",
            chat_id="dm:peer",
            sender="peer",
            content="",
            metadata={"account_id": row.record.id, "chat_type": "private"},
        )
    )
    assert message is not None
    view = turn_context_view(tmp_path, "mira", message.metadata["thread_id"])

    async def prepare():
        return await prepare_context_window_request(
            sessions=host.manager,
            session_key=message.session_key,
            view=view,
            msg=message,
            provider=host.provider,
            model="fixture",
            max_tokens=100,
            tools=host.loop.tools,
            search_enabled=False,
            render_prompt=host.loop._reasoner.render_prompt,
        )

    before = await prepare()
    assert "user_only" in {schema["function"]["name"] for schema in before.schemas}
    accounts.set_response_rules(row.record.id, AccountResponseRules())
    after = await prepare()
    assert "user_only" not in {schema["function"]["name"] for schema in after.schemas}
    for request in (before, after):
        prompt = str(request.messages)
        assert all(secret not in prompt for secret in SECRETS)
    assert host.provider.requests == []
