"""Read-only resolution of a send target to its real inbound conversation."""

from dataclasses import dataclass
from typing import Literal

from .models import AccountRecord, account_serves_channel

ACCOUNT_RESOLVE_METHOD = "account.resolve"


@dataclass(frozen=True)
class AccountRoute:
    """Canonical destination before delivery; never evidence of a successful send.

    ``account.resolve`` receives account_id and AccountTarget.to_payload(). It
    validates the same destination as account.send without sending or widening
    platform permissions. Topic IDs remain separate from chat_id.
    This address is distinct from the private conversation tool grant.
    """

    channel: str
    chat_id: str
    chat_type: Literal["private", "group"] = "private"
    message_thread_id: int | None = None

    def to_payload(self) -> dict[str, object]:
        """Serialize the resolver's canonical inbound address."""
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "message_thread_id": self.message_thread_id,
        }

    @classmethod
    def for_account(cls, value: object, record: AccountRecord) -> "AccountRoute":
        """Reject missing/foreign addresses rather than guessing from a target ID."""
        if not isinstance(value, dict):
            raise ValueError("目标会话地址必须是对象")
        channel, chat_id, chat_type = (
            value.get("channel"),
            value.get("chat_id"),
            value.get("chat_type"),
        )
        topic = value.get("message_thread_id")
        if (
            not isinstance(channel, str)
            or not channel.strip()
            or not isinstance(chat_id, str)
            or not chat_id.strip()
            or not isinstance(chat_type, str)
            or chat_type not in {"private", "group"}
            or not account_serves_channel(record, channel.strip())
            or (
                topic is not None
                and (type(topic) is not int or topic <= 0 or chat_type != "group")
            )
        ):
            raise ValueError("目标会话地址与账号不一致")
        return cls(
            channel.strip(),
            chat_id.strip(),
            "group" if chat_type == "group" else "private",
            topic,
        )
