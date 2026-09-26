"""Account delivery records each explicit target independently of turn commits."""

from __future__ import annotations

import asyncio
import pytest

from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.accounts.target_contract import UncertainDeliveryError


class _Rpc:
    def __init__(self, ledger: AccountDeliveryLedger, plugin_id: str = "chat") -> None:
        self.ledger = ledger
        self.plugin_id = plugin_id
        self.calls: list[tuple[str, dict]] = []
        self.failure: BaseException | None = None
        self.missing_receipt = False

    def resolve(self, name: str):
        async def handle(payload: dict):
            self.calls.append((name, payload))
            if name.endswith("account.targets"):
                return {"scope": "known", "items": [{"id": "42"}]}
            [latest] = self.ledger.list_for_role("mira")[-1:]
            assert latest.status == "pending"
            if self.failure is not None:
                raise self.failure
            if self.missing_receipt:
                return {}
            return {"message_id": f"receipt-{len(self.calls)}"}

        return (self.plugin_id, handle)


def _service(tmp_path, plugin_id: str = "chat"):
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id in {"mira", "other"})
    accounts.set_plugin_enabled(plugin_id, True)
    account = accounts.register(
        plugin_id=plugin_id,
        platform=plugin_id,
        platform_account_id="bot",
        config_ref="bot",
        token="live",
    )
    account_id = account.record.id
    accounts.assign(account_id, "mira")
    accounts.report(account_id, "live", connection="online")
    ledger = AccountDeliveryLedger(tmp_path)
    rpc = _Rpc(ledger, plugin_id)
    return AccountDelivery(accounts, rpc, ledger), accounts, rpc, ledger, account_id


@pytest.mark.asyncio
async def test_each_target_has_durable_receipt_even_if_turn_later_fails(
    tmp_path,
) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    state: dict[str, bool] = {}
    with pytest.raises(RuntimeError, match="later model step"):
        with account_delivery_scope(state):
            first = await service.send(
                account_id, "mira", "private", "42", "private secret", None
            )
            second = await service.send(
                account_id, "mira", "group", "43", "another secret", None
            )
            raise RuntimeError("later model step failed")

    attempts = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert state == {"sent": True}
    assert len(attempts) == 2
    assert {row.attempt_id for row in attempts} == {first.attempt_id, second.attempt_id}
    assert {
        (row.target_id, row.platform_message_id, row.status) for row in attempts
    } == {
        ("42", first.platform_message_id, "sent"),
        ("43", second.platform_message_id, "sent"),
    }
    assert len(rpc.calls) == 2
    database = (tmp_path / "account_deliveries.sqlite3").read_bytes()
    assert b"private secret" not in database
    assert b"another secret" not in database


@pytest.mark.asyncio
async def test_rejected_and_unowned_attempts_record_failure(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(PermissionError):
            await service.send(account_id, "other", "private", "42", "hello", None)
    rpc.failure = ValueError("platform rejected target")
    with account_delivery_scope(state):
        with pytest.raises(ValueError, match="platform rejected"):
            await service.send(account_id, "mira", "private", "42", "hello", None)

    attempts = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert [(row.status, row.error) for row in attempts] == [("failed", "ValueError")]
    unauthorized = AccountDeliveryLedger(tmp_path).list_for_role("other")
    assert [(row.status, row.error) for row in unauthorized] == [
        ("failed", "PermissionError")
    ]
    assert len(rpc.calls) == 1
    assert state == {}


@pytest.mark.asyncio
async def test_uncertain_timeout_remains_pending(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.failure = TimeoutError("reply lost")
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(TimeoutError):
            await service.send(account_id, "mira", "private", "42", "hello", None)
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert attempt.status == "pending"
    assert attempt.platform_message_id is None
    assert attempt.error == "TimeoutError"
    assert state == {"sent": True}


@pytest.mark.asyncio
async def test_missing_platform_receipt_remains_pending(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.failure = UncertainDeliveryError("receipt missing")
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(UncertainDeliveryError):
            await service.send(account_id, "mira", "private", "42", "hello", None)
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.status, attempt.error) == ("pending", "UncertainDeliveryError")
    assert state == {"sent": True}


@pytest.mark.asyncio
async def test_empty_plugin_receipt_suppresses_implicit_reply(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.missing_receipt = True
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(RuntimeError, match="结果不确定"):
            await service.send(account_id, "mira", "private", "42", "hello", None)
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.status, attempt.error) == ("pending", "MissingReceipt")
    assert state == {"sent": True}


@pytest.mark.asyncio
async def test_cancelled_plugin_call_suppresses_implicit_reply(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.failure = asyncio.CancelledError()
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(asyncio.CancelledError):
            await service.send(account_id, "mira", "private", "42", "hello", None)
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.status, attempt.error) == ("pending", "CancelledError")
    assert state == {"sent": True}
