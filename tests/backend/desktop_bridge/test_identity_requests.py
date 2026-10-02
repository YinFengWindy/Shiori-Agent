"""Desktop identity commands list, pair through the shared store, and unbind."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from core.accounts import AccountRegistry
from shiori_sdk.accounts.models import AccountRecord
from core.channel_avatars import AvatarKey, ChannelAvatarStore
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
    handler = DesktopIdentityRequestHandler(
        identities, ChannelAvatarStore(tmp_path), AccountRegistry({"mira"}.__contains__)
    )

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
                "avatar_abs": None,
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


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


def _registry() -> tuple[AccountRegistry, AccountRecord, AccountRecord]:
    """A registry with a QQ account and a Feishu application of role ``mira``."""
    accounts = AccountRegistry({"mira"}.__contains__)
    qq = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="10001",
        config_ref="qq-1",
        token="q",
        role_id="mira",
    )
    feishu = accounts.register(
        plugin_id="feishu",
        platform="feishu",
        platform_account_id="feishu:cli_a",
        config_ref="feishu:cli_a",
        token="f",
        role_id="mira",
    )
    return accounts, qq.record, feishu.record


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["platform", "account"])
async def test_listed_identity_shows_its_cached_platform_avatar(
    tmp_path, scope
) -> None:
    identities = UserIdentityStore(tmp_path)
    avatars = ChannelAvatarStore(tmp_path)
    accounts, qq, feishu = _registry()
    handler = DesktopIdentityRequestHandler(identities, avatars, accounts)
    record = qq if scope == "platform" else feishu
    # The pairing chat is on another transport than the one that cached the avatar.
    chat_channel = "qq" if scope == "platform" else "feishu:old"
    _ = identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id="902",
        scope=scope,
        chat=IdentityChat(record.id, chat_channel, "902"),
    )
    # The same ID on another plugin's channel is someone else.
    other = "feishu:cli_a" if scope == "platform" else "qq"
    avatars.save(AvatarKey("sender", other, "902"), _png(), plugin_id="x")

    async def listed_avatar() -> str | None:
        result = await handler.handle("identities.list", {})
        assert result is not None
        return result["identities"][0]["avatar_abs"]

    assert await listed_avatar() is None
    # Found through the account the binding applies to, not a recorded chat.
    channel = "qq" if scope == "platform" else "feishu:feishu:cli_a"
    avatars.save(
        AvatarKey("sender", channel, "902"), _png(), plugin_id=record.plugin_id
    )
    assert await listed_avatar() == avatars.index().sender(channel, "902")
    assert await listed_avatar() is not None
