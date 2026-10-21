"""Live account tool authorization, separate from durable sender identity."""

from shiori_sdk.accounts.models import account_serves_channel
from shiori_sdk.channels.projection import ACCOUNT_FULL_TOOLS_KEY
from shiori_sdk.channels.chat_types import is_group_chat_type
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.messages import InboundMessage

from .registry import AccountRegistry


def account_allows_full_tools(
    accounts: AccountRegistry | None, message: InboundMessage, *, role_id: str = ""
) -> bool:
    """Recheck the host-admitted route against the current account, never history.

    A queued message's admission flag alone is insufficient after revocation,
    disconnection, deletion or a change of role. This changes tools, not context.
    """
    metadata = message.metadata
    if (
        accounts is None
        or metadata.get(ACCOUNT_FULL_TOOLS_KEY) is not True
        or metadata.get("source") not in {"role_account", "background_result"}
    ):
        return False
    owner = str(metadata.get("role_id") or "")
    if not owner or (role_id and role_id != owner):
        return False
    try:
        account = accounts.get(str(metadata.get("account_id") or ""))
    except KeyError:
        return False
    rules = account.record.response_rules
    return (
        account.record.role_id == owner
        and account.runtime_active
        and account.connection == "online"
        and "full_tools" in account.capabilities
        and account.tool_conversation is not None
        and account.tool_conversation.channel == message.channel
        and account.tool_conversation.chat_id == message.chat_id
        and rules.allow_full_tools is True
        and (
            rules.group_enabled
            if is_group_chat_type(metadata.get("chat_type"))
            else rules.private_enabled
        )
        and message.sender not in rules.blocked_sender_ids
        and account_serves_channel(account.record, message.channel)
        and metadata.get("thread_id")
        == network_thread_id(owner, message.channel, message.chat_id)
        and message.session_key == f"role:{owner}"
    )
