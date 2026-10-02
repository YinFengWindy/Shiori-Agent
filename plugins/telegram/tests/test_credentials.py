"""Draft Token validation never persists or echoes credentials."""

from unittest.mock import AsyncMock, patch
from shiori_sdk.testing.extensions import FakeConfig

import pytest

from plugins.telegram.backend.credentials import verify_bot_token, resolve_token


def test_stored_token_reference_uses_the_injected_runtime_resolver():
    config = FakeConfig()
    config.references["${BOT_TOKEN}"] = " 123:secret "
    assert resolve_token("${BOT_TOKEN}", config.resolve_reference) == "123:secret"
    assert resolve_token("${UNSET}", config.resolve_reference) == ""


@pytest.mark.asyncio
async def test_verify_bot_token_returns_only_platform_identity():
    identity = type(
        "Identity", (), {"id": 123, "full_name": "First Bot", "username": "first_bot"}
    )()
    with patch("plugins.telegram.backend.credentials.Bot") as bot_type:
        bot_type.return_value.__aenter__ = AsyncMock(
            return_value=type(
                "FakeBot", (), {"get_me": AsyncMock(return_value=identity)}
            )()
        )
        result = await verify_bot_token(
            {"token": "123:secret"}, FakeConfig().resolve_reference
        )
    assert result == {"bot_id": "123", "name": "First Bot", "username": "first_bot"}
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_verify_bot_token_rejects_empty_draft():
    with pytest.raises(ValueError, match="required"):
        await verify_bot_token({"token": " "}, FakeConfig().resolve_reference)
