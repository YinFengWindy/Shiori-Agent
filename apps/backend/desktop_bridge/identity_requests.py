"""Bridge commands over the desktop user's bound platform identities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.accounts import AccountRegistry
from shiori_sdk.accounts.models import AccountRecord, account_serves_channel
from core.channel_avatars import AvatarIndex, ChannelAvatarStore
from core.identity import UserIdentity, UserIdentityStore


def identity_avatar(
    identity: UserIdentity, avatars: AvatarIndex, accounts: Sequence[AccountRecord]
) -> str | None:
    """The bound identity's cached platform avatar file; None when none is cached.

    Nothing is fetched for this: a channel plugin caches a sender's avatar
    when their message arrives (#514). A cached sender avatar counts when its
    channel is one the binding is recognised on: a channel carried by an
    account the binding applies to (every account of the plugin for
    ``platform`` scope, the bound account for ``account`` scope), or one of
    its known private chats. The most recently fetched one wins.
    """
    applicable = [record for record in accounts if identity.applies_to(record)]
    chat_channels = {chat.channel for chat in identity.chats}
    return next(
        (
            path
            for channel, path in avatars.sender_avatars(identity.user_id)
            if channel in chat_channels
            or any(account_serves_channel(record, channel) for record in applicable)
        ),
        None,
    )


def _serialize(
    identity: UserIdentity, avatars: AvatarIndex, accounts: Sequence[AccountRecord]
) -> dict[str, Any]:
    """One binding as the desktop lists it, with ``identity_avatar`` as ``avatar_abs``."""
    return {
        "id": identity.id,
        "plugin_id": identity.plugin_id,
        "user_id": identity.user_id,
        "scope": identity.scope,
        "account_id": identity.account_id,
        "bound_at": identity.bound_at,
        "avatar_abs": identity_avatar(identity, avatars, accounts),
    }


class DesktopIdentityRequestHandler:
    """Lists and unbinds identities and issues pairing codes for the desktop.

    Methods: ``identities.list`` -> ``{"identities": [...]}``;
    ``identities.pairing.create`` -> ``{"code", "expires_at"}`` (ISO time);
    ``identities.unbind`` with ``identity_id`` -> ``{"identity_id"}``.
    """

    def __init__(
        self,
        identities: UserIdentityStore,
        avatars: ChannelAvatarStore,
        accounts: AccountRegistry,
    ) -> None:
        self._identities = identities
        self._avatars = avatars
        self._accounts = accounts

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one identity request; None for methods it does not own."""
        if method == "identities.list":
            avatars = self._avatars.index()
            accounts = [account.record for account in self._accounts.list()]
            return {
                "identities": [
                    _serialize(item, avatars, accounts)
                    for item in self._identities.list()
                ]
            }
        if method == "identities.pairing.create":
            code = self._identities.create_pairing_code()
            return {"code": code.code, "expires_at": code.expires_at.isoformat()}
        if method == "identities.unbind":
            identity_id = str(payload.get("identity_id") or "").strip()
            if not identity_id:
                raise ValueError("identity_id 不能为空")
            self._identities.unbind(identity_id)
            return {"identity_id": identity_id}
        return None
