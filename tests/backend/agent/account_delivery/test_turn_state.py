"""Explicit send signal stays inside the active model attempt."""

from agent.account_delivery.turn_state import (
    account_delivery_scope,
    mark_account_delivery_sent,
)


def test_account_delivery_signal_is_scoped() -> None:
    first: dict[str, bool] = {}
    second: dict[str, bool] = {}
    with account_delivery_scope(first):
        mark_account_delivery_sent()
    mark_account_delivery_sent()
    with account_delivery_scope(second):
        assert second == {}
    assert first == {"sent": True}
    assert second == {}
