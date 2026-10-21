"""A remembered grant never replaces live connection ownership and policy."""

from dataclasses import replace

import pytest

from core.accounts import AccountRegistry
from core.accounts.tool_access import account_allows_full_tools
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.conversation import AccountConversation
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.messages import InboundMessage


@pytest.fixture
def granted():
    accounts = AccountRegistry(lambda _: True)
    account = accounts.register(
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
        account.record.id,
        "live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountConversation("grok_bot_one", "dm:peer"),
    )
    message = InboundMessage(
        channel="grok_bot_one",
        sender="peer",
        chat_id="dm:peer",
        content="hi",
        metadata={
            "source": "role_account",
            "account_id": account.record.id,
            "role_id": "mira",
            "thread_id": network_thread_id("mira", "grok_bot_one", "dm:peer"),
            "session_key_override": "role:mira",
            "account_full_tools": True,
        },
    )
    return accounts, message


def test_current_rules_revoke_queued_and_remembered_grants(granted):
    accounts, message = granted
    assert account_allows_full_tools(accounts, message)
    accounts.set_response_rules(message.metadata["account_id"], AccountResponseRules())
    assert not account_allows_full_tools(accounts, message)


@pytest.mark.parametrize(
    "changes",
    [
        {"role_id": "other"},
        {"thread_id": "thread:other"},
        {"account_id": "grok_bot:other"},
        {"source": "external_turn"},
        {"account_full_tools": "true"},
        {"session_key_override": "role:other"},
    ],
)
def test_forged_or_cross_role_route_cannot_gain_permissions(granted, changes):
    accounts, message = granted
    assert not account_allows_full_tools(
        accounts, replace(message, metadata={**message.metadata, **changes})
    )
    assert not account_allows_full_tools(accounts, message, role_id="other")


def test_disconnected_or_unsupported_accounts_are_restricted(granted):
    accounts, message = granted
    account_id = message.metadata["account_id"]
    accounts.report(
        account_id, "live", connection="offline", capabilities=frozenset({"full_tools"})
    )
    assert not account_allows_full_tools(accounts, message)


def test_rebinding_then_regranting_does_not_reauthorize_old_peer(granted):
    accounts, old = granted
    account_id = old.metadata["account_id"]
    fence = accounts.authorize(account_id, "mira")
    accounts.set_response_rules(account_id, AccountResponseRules())
    accounts.report(
        account_id,
        "live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountConversation("grok_bot_one", "dm:new-peer"),
    )
    accounts.set_response_rules(account_id, AccountResponseRules(allow_full_tools=True))
    assert accounts.validate_access(fence), "the plugin token did not change"
    assert not account_allows_full_tools(accounts, old)
    new = replace(
        old,
        sender="new-peer",
        chat_id="dm:new-peer",
        metadata={
            **old.metadata,
            "thread_id": network_thread_id("mira", "grok_bot_one", "dm:new-peer"),
        },
    )
    assert account_allows_full_tools(accounts, new)


def test_missing_or_foreign_canonical_route_does_not_grant_access(granted):
    accounts, message = granted
    account_id = message.metadata["account_id"]
    accounts.report(
        account_id, "live", connection="online", capabilities=frozenset({"full_tools"})
    )
    assert not account_allows_full_tools(accounts, message)
    with pytest.raises(ValueError, match="账号不一致"):
        accounts.report(
            account_id,
            "live",
            connection="online",
            capabilities=frozenset({"full_tools"}),
            tool_conversation=AccountConversation("other", "dm:peer"),
        )
    assert not account_allows_full_tools(accounts, message)
    accounts.report(account_id, "live", connection="online")
    assert not account_allows_full_tools(accounts, message)
