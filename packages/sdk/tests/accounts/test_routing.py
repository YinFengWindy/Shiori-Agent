"""Pre-send routes are canonical, account-scoped and separate from tool grants."""

import pytest

from shiori_sdk.accounts.models import AccountRecord
from shiori_sdk.accounts.routing import AccountRoute
from shiori_sdk.accounts.conversation import AccountConversation


def test_group_route_keeps_topic_and_cannot_be_used_as_private_tool_conversation():
    record = AccountRecord("telegram:a", "telegram", "telegram", "a", "a", "mira")
    route = AccountRoute("telegram_a", "-42", "group", 27)
    assert AccountRoute.for_account(route.to_payload(), record) == route
    with pytest.raises(ValueError):
        AccountConversation.for_account(route.to_payload(), record)


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
