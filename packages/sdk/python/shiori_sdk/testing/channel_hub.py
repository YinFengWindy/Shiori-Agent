"""Explicit channel routing decisions and delivery receipts for plugin tests."""

from shiori_sdk.messages import InboundMessage, OutboundMessage


class FakeChannelHub:
    """Record requests without constructing roles, identities or conversation storage."""

    def __init__(
        self,
        *,
        allowed: bool = True,
        blocked: bool = False,
        session_key: str = "role:mira",
    ):
        self.allowed, self.blocked, self.session_key = allowed, blocked, session_key
        self.deliveries: list[dict[str, object]] = []

    def is_sender_allowed(self, **kwargs: object) -> bool:
        """Return the fixture's selected admission decision."""
        return self.allowed and not self.blocked

    def is_sender_blocked(self, **kwargs: object) -> bool:
        """Return the fixture's selected blacklist decision."""
        return self.blocked

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        """Leave routing projection to explicit test metadata."""
        return message

    def route_account_inbound(
        self, message: InboundMessage, **kwargs: object
    ) -> InboundMessage | None:
        """Return a fixture-selected acceptance without host policy."""
        return message if self.is_sender_allowed() else None

    def claim_pairing(self, message: InboundMessage, *, scope: str) -> bool:
        """No implicit fixture pairing codes exist."""
        return False

    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str:
        """Return the test-selected role session."""
        return self.session_key

    def resolve_account_runtime_session_key(self, account_id: str) -> str:
        """Return the test-selected account owner session."""
        return self.session_key

    def mark_delivery(
        self,
        message: OutboundMessage,
        *,
        default_channel: str,
        delivery_status: str,
        external_message_id: str = "",
        via_account: dict[str, str] | None = None,
    ) -> None:
        """Record the observable receipt; actual persistence is a host integration test."""
        self.deliveries.append(
            {
                "session_key": message.metadata.get(
                    "session_key_override", self.session_key
                ),
                "message_id": message.committed_message_id,
                "thread_id": message.metadata.get("thread_id", ""),
                "delivery_status": delivery_status,
                "external_message_id": external_message_id,
            }
        )
