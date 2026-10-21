"""Canonical conversation addresses returned by confirmed account sends."""

from dataclasses import dataclass
from typing import Literal

from .models import AccountRecord, account_serves_channel

ACCOUNT_CONVERSATION_KEY = "conversation"


@dataclass(frozen=True)
class AccountConversation:
    """The actual channel chat that accepted a private account send.

    Platform target IDs are not necessarily chat IDs. A sending plugin returns
    this address only after resolving its target to the same chat used on
    inbound messages; the host uses it to record the outgoing conversation.
    """

    channel: str
    chat_id: str
    chat_type: Literal["private"] = "private"

    def to_payload(self) -> dict[str, str]:
        """Return the JSON value carried by ``account.send`` receipts."""
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
        }

    @classmethod
    def for_account(cls, value: object, record: AccountRecord) -> "AccountConversation":
        """Validate a plugin address against the actual sending account."""
        if not isinstance(value, dict):
            raise ValueError("投递会话地址必须是对象")
        channel, chat_id = value.get("channel"), value.get("chat_id")
        if (
            not isinstance(channel, str)
            or not channel.strip()
            or not isinstance(chat_id, str)
            or not chat_id.strip()
            or value.get("chat_type") != "private"
            or not account_serves_channel(record, channel.strip())
        ):
            raise ValueError("投递会话地址与账号不一致或不是私聊")
        return cls(channel.strip(), chat_id.strip())
