"""Account attempt status survives process-local ledger instances."""

from __future__ import annotations

import pytest

from core.accounts.delivery_ledger import AccountDeliveryLedger


def test_pending_attempt_and_terminal_results_survive_reopen(tmp_path) -> None:
    ledger = AccountDeliveryLedger(tmp_path)
    sent = ledger.begin(
        role_id="mira",
        account_id="account-1",
        target_kind="group",
        target_id="42",
        target_options={"message_thread_id": 7},
        source="proactive",
    )
    failed = ledger.begin(
        role_id="mira",
        account_id="account-1",
        target_kind="private",
        target_id="43",
        target_options={},
        source="passive_tool",
    )
    reopened = AccountDeliveryLedger(tmp_path)
    assert reopened.get(sent.attempt_id).status == "pending"
    assert reopened.get(sent.attempt_id).target_options == {"message_thread_id": 7}
    reopened.mark_uncertain(sent.attempt_id, "TimeoutError")
    assert reopened.get(sent.attempt_id).status == "pending"
    assert reopened.get(sent.attempt_id).error == "TimeoutError"
    reopened.mark_sent(sent.attempt_id, "platform-9")
    reopened.mark_failed(failed.attempt_id, "ValueError")

    persisted = AccountDeliveryLedger(tmp_path)
    assert persisted.get(sent.attempt_id).platform_message_id == "platform-9"
    assert persisted.get(failed.attempt_id).error == "ValueError"
    assert {row.status for row in persisted.list_for_role("mira")} == {"sent", "failed"}
    with pytest.raises(RuntimeError, match="已完成"):
        persisted.mark_failed(sent.attempt_id, "late")
