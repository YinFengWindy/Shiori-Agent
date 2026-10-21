"""Confirmed sends may name canonical chats without guessing from target IDs."""

import pytest
from shiori_sdk.accounts.models import AccountRecord
from shiori_sdk.accounts.conversation import AccountConversation


@pytest.fixture
def record():
    return AccountRecord("grok_bot:a", "grok_bot", "grok_bot", "a", "a", "mira")


def test_canonical_private_address_roundtrips(record):
    address = AccountConversation("grok_bot_a", "dm:peer")
    assert AccountConversation.for_account(address.to_payload(), record) == address


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"channel": "other", "chat_id": "dm:peer", "chat_type": "private"},
        {"channel": "grok_bot_a", "chat_id": "dm:peer", "chat_type": "group"},
        {"channel": "grok_bot_a", "chat_id": " ", "chat_type": "private"},
    ],
)
def test_invalid_or_foreign_address_is_rejected(record, payload):
    with pytest.raises(ValueError):
        AccountConversation.for_account(payload, record)
