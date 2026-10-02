"""Explicit channel routing decisions and delivery receipts for plugin tests."""

from collections.abc import Callable
from dataclasses import replace

from shiori_sdk.channels.chat_types import is_group_chat_type
from shiori_sdk.channels.message_source import addresses_account
from shiori_sdk.messages import InboundMessage, OutboundMessage


class FakeChannelHub:
    """Admit and project input like the host hub, with fixture-selected decisions.

    No roles, accounts or conversation storage exist: ``allowed`` / ``blocked``
    stand in for the host's binding and blocklist checks, ``role_id`` and
    ``session_key`` name the bound role, and ``pairing_code`` is the pending
    code a private message may claim. Like the host, a group message that does
    not address ``platform_account_id`` starts no turn; with ``listening`` it
    is handed to ``on_heard`` as kept in the group's listening records.
    """

    def __init__(
        self,
        *,
        allowed: bool = True,
        blocked: bool = False,
        session_key: str = "role:mira",
        role_id: str = "mira",
        pairing_code: str | None = None,
        platform_account_id: str = "",
        listening: bool = False,
    ):
        self.allowed, self.blocked, self.session_key = allowed, blocked, session_key
        self.role_id, self.pairing_code = role_id, pairing_code
        self.platform_account_id, self.listening = platform_account_id, listening
        # Every message offered to account routing, before any decision.
        self.offered: list[InboundMessage] = []
        self.deliveries: list[dict[str, object]] = []
        # (sender, content, scope) of every pairing attempt, claimed or not.
        self.pairings: list[tuple[str, str, str]] = []
        self._seen_external_ids: set[str] = set()

    def is_sender_allowed(self, **kwargs: object) -> bool:
        """Return the fixture's selected admission decision."""
        return self.allowed and not self.blocked

    def is_sender_blocked(self, **kwargs: object) -> bool:
        """Return the fixture's selected blacklist decision."""
        return self.blocked

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        """Project admitted input onto the bound role; like the host, refuse the rest."""
        if message.channel == "desktop":
            return message
        routed = self.route_account_inbound(message)
        if routed is None:
            raise PermissionError("接收账号未授权此消息")
        return routed

    def route_account_inbound(
        self,
        message: InboundMessage,
        *,
        on_heard: Callable[[InboundMessage], None] | None = None,
    ) -> InboundMessage | None:
        """Return the projected message, or None when it starts no turn."""
        self.offered.append(message)
        if not self.is_sender_allowed():
            return None
        if is_group_chat_type(message.metadata.get("chat_type")) and not (
            addresses_account(message.metadata, self.platform_account_id)
        ):
            if self.listening and message.content.strip() and on_heard is not None:
                on_heard(self._project(message))
            return None
        return self._project(message)

    def _project(self, message: InboundMessage) -> InboundMessage:
        """Stamp the host's role-session fields and mark replayed platform ids."""
        metadata = dict(message.metadata)
        external_message_id = str(
            metadata.get("external_message_id") or metadata.get("message_id") or ""
        ).strip()
        if external_message_id:
            metadata["external_message_id"] = external_message_id
            # The host marks input whose platform id its thread already stored.
            if external_message_id in self._seen_external_ids:
                metadata["conversation_duplicate"] = True
            self._seen_external_ids.add(external_message_id)
        metadata["role_id"] = self.role_id
        metadata["session_key_override"] = self.session_key
        metadata["transport_channel"] = message.channel
        metadata["transport_chat_id"] = message.chat_id
        metadata["sender_id"] = message.sender
        metadata.setdefault("source", "role_account")
        return replace(message, media=list(message.media), metadata=metadata)

    def claim_pairing(self, message: InboundMessage, *, scope: str) -> bool:
        """Consume the fixture's pairing code; a blocked sender cannot pair."""
        self.pairings.append((message.sender, message.content, scope))
        return (
            not self.blocked
            and self.pairing_code is not None
            and message.content == self.pairing_code
        )

    def delivery_statuses(self) -> list[object]:
        """The ``delivery_status`` of every recorded receipt, in order."""
        return [item["delivery_status"] for item in self.deliveries]

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
                "chat_id": message.chat_id,
                "message_id": message.committed_message_id,
                "thread_id": message.metadata.get("thread_id", ""),
                "delivery_status": delivery_status,
                "external_message_id": external_message_id,
                "via_account": via_account,
            }
        )
