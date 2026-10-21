"""The fixed Bot's directory and standard account-send adapter."""

from uuid import uuid4
from .accounts import GrokAccounts
from .protocol import BotMessage


class GrokDelivery:
    """Discover and send to the configured Bot through the host account tools."""

    def __init__(self, accounts: GrokAccounts) -> None:
        self.accounts = accounts

    async def targets(self, payload: dict[str, object]) -> dict[str, object]:
        """Only the single configured private target belongs to this account."""
        if payload.get("kind") not in {"known", "friends"}:
            raise ValueError("Grok 连接只支持当前 Bot 的私聊目标")
        config = self.accounts.connection_for(payload).config
        return {
            "coverage": "configured_bot",
            "targets": [
                {
                    "id": config.peer_id,
                    "name": config.peer_name,
                    "chat_id": config.chat_id,
                    "target_kind": "private",
                }
            ],
        }

    async def send(self, payload: dict[str, object]) -> dict[str, object]:
        """Refuse other targets and unsupported media before causing side effects."""
        connection = self.accounts.connection_for(payload)
        if (
            payload.get("target_kind") != "private"
            or payload.get("target_id") != connection.config.peer_id
        ):
            raise ValueError("Grok 连接仅支持当前配置的 Bot 私聊")
        if any(
            payload.get(key)
            for key in ("group_id", "message_thread_id", "mention_ids", "media")
        ):
            raise ValueError("Grok 连接不支持群聊、话题、提及或媒体")
        message = BotMessage.parse(
            {"message_id": "shiori:" + uuid4().hex, "text": payload.get("message")}
        )
        return await connection.send(message)
