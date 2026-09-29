"""Desktop identity commands list, pair through the shared store, and unbind."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.accounts import AccountRecord
from core.identity import IdentityChat, UserIdentityStore
from desktop_bridge.identity_requests import DesktopIdentityRequestHandler

_ACCOUNT = AccountRecord(
    id="demo:1",
    plugin_id="demo",
    platform="demo",
    platform_account_id="1",
    config_ref="a",
    role_id="mira",
)


@pytest.mark.asyncio
async def test_identity_requests_list_pair_and_unbind(tmp_path) -> None:
    identities = UserIdentityStore(tmp_path)
    handler = DesktopIdentityRequestHandler(identities)

    created = await handler.handle("identities.pairing.create", {})
    assert created is not None
    assert datetime.fromisoformat(created["expires_at"]) > datetime.now(timezone.utc)
    # Channel intake consumes the code through the same store.
    identity = identities.pair(
        created["code"],
        record=_ACCOUNT,
        user_id="902",
        scope="platform",
        chat=IdentityChat(_ACCOUNT.id, "demo", "902"),
    )
    assert identity is not None
    assert await handler.handle("identities.list", {}) == {
        "identities": [
            {
                "id": identity.id,
                "plugin_id": "demo",
                "user_id": "902",
                "scope": "platform",
                "account_id": "",
                "bound_at": identity.bound_at,
            }
        ]
    }

    assert await handler.handle("identities.unbind", {"identity_id": identity.id}) == {
        "identity_id": identity.id
    }
    assert await handler.handle("identities.list", {}) == {"identities": []}
    with pytest.raises(ValueError, match="identity_id"):
        await handler.handle("identities.unbind", {})
    assert await handler.handle("accounts.list", {}) is None
