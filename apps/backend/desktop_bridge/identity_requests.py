"""Bridge commands over the desktop user's bound platform identities."""

from __future__ import annotations

from typing import Any

from core.identity import UserIdentity, UserIdentityStore


def _serialize(identity: UserIdentity) -> dict[str, Any]:
    return {
        "id": identity.id,
        "plugin_id": identity.plugin_id,
        "user_id": identity.user_id,
        "scope": identity.scope,
        "account_id": identity.account_id,
        "bound_at": identity.bound_at,
    }


class DesktopIdentityRequestHandler:
    """Lists and unbinds identities and issues pairing codes for the desktop.

    Methods: ``identities.list`` -> ``{"identities": [...]}``;
    ``identities.pairing.create`` -> ``{"code", "expires_at"}`` (ISO time);
    ``identities.unbind`` with ``identity_id`` -> ``{"identity_id"}``.
    """

    def __init__(self, identities: UserIdentityStore) -> None:
        self._identities = identities

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one identity request; None for methods it does not own."""
        if method == "identities.list":
            return {
                "identities": [_serialize(item) for item in self._identities.list()]
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
