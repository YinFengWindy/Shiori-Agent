"""Pre-send routes are canonical, account-scoped and separate from tool grants."""

import pytest

from shiori_sdk.accounts.models import AccountRecord
from shiori_sdk.accounts.routing import AccountRoute


def test_group_route_keeps_topic_and_cannot_be_a_private_grant():
    record = AccountRecord("telegram:a", "telegram", "telegram", "a", "a", "mira")
    route = AccountRoute("telegram_a", "-42", "group", 27)
    assert AccountRoute.for_account(route.to_payload(), record) == route
    with pytest.raises(ValueError):
        AccountRoute.for_private(route.to_payload(), record)


@pytest.mark.parametrize(
    "change",
    [
        {"channel": "qq"},
        {"chat_id": ""},
        {"chat_type": ""},
        {"chat_type": []},
        {"message_thread_id": True},
        {"message_thread_id": 0},
        {"message_thread_id": "27"},
        {"chat_type": "private"},
    ],
)
def test_incomplete_foreign_or_invalid_topic_address_is_refused(change):
    record = AccountRecord("telegram:a", "telegram", "telegram", "a", "a", "mira")
    payload = {**AccountRoute("telegram_a", "-42", "group", 27).to_payload(), **change}
    with pytest.raises(ValueError):
        AccountRoute.for_account(payload, record)


def test_private_receipt_roundtrips_and_rejects_a_foreign_or_group_address():
    record = AccountRecord("grok_bot:a", "grok_bot", "grok_bot", "a", "a", "mira")
    address = AccountRoute("grok_bot_a", "dm:peer")
    assert AccountRoute.for_private(address.to_payload(), record) == address
    for payload in (
        {},
        {"channel": "other", "chat_id": "dm:peer", "chat_type": "private"},
        {"channel": "grok_bot_a", "chat_id": "dm:peer", "chat_type": "group"},
        {"channel": "grok_bot_a", "chat_id": " ", "chat_type": "private"},
    ):
        with pytest.raises(ValueError):
            AccountRoute.for_private(payload, record)
