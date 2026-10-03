"""Account delivery records each explicit target independently of turn commits."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys
import pytest

from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from shiori_sdk.accounts.targets import AccountTarget, UncertainDeliveryError
from core.identity import IdentityChat, UserIdentityStore


def test_service_import_does_not_initialize_the_plugin_kernel(tmp_path: Path) -> None:
    """A fresh interpreter must import delivery without any fixture preloading."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys\n"
            "from agent.account_delivery.service import AccountDelivery\n"
            "assert AccountDelivery.__name__ == 'AccountDelivery'\n"
            "assert 'agent.plugin_host' not in sys.modules\n",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


class _Rpc:
    def __init__(self, ledger: AccountDeliveryLedger, plugin_id: str = "chat") -> None:
        self.ledger = ledger
        self.plugin_id = plugin_id
        self.calls: list[tuple[str, dict]] = []
        self.failure: BaseException | None = None
        self.missing_receipt = False
        self.via: dict | None = None

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
            receipt = {"message_id": f"receipt-{len(self.calls)}"}
            return receipt if self.via is None else {**receipt, "via_account": self.via}

        return (self.plugin_id, handle)


def _service(tmp_path, plugin_id: str = "chat"):
    accounts = AccountRegistry(lambda role_id: role_id in {"mira", "other"})
    account = accounts.register(
        plugin_id=plugin_id,
        platform=plugin_id,
        platform_account_id="bot",
        config_ref="bot",
        token="live",
        role_id="mira",
    )
    account_id = account.record.id
    accounts.report(account_id, "live", connection="online")
    ledger = AccountDeliveryLedger(tmp_path)
    rpc = _Rpc(ledger, plugin_id)
    return (
        AccountDelivery(accounts, rpc, ledger, UserIdentityStore(tmp_path)),
        accounts,
        rpc,
        ledger,
        account_id,
    )


@pytest.mark.asyncio
async def test_each_target_has_durable_receipt_even_if_turn_later_fails(
    tmp_path,
) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    state: dict[str, bool] = {}
    with pytest.raises(RuntimeError, match="later model step"):
        with account_delivery_scope(state):
            first = await service.send(
                "chat", "mira", AccountTarget("private", "42"), "private secret"
            )
            second = await service.send(
                "chat", "mira", AccountTarget("group", "43"), "another secret"
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


_VIA = {
    "platform": "chat",
    "platform_account_id": "bot",
    "display_name": "Mira Bot",
    "prefix": "Chat 机器人「Mira Bot」",
}


@pytest.mark.asyncio
async def test_every_attempt_is_recorded_even_without_an_account_on_the_channel(
    tmp_path,
) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(LookupError, match="渠道 chat"):
            await service.send("chat", "other", AccountTarget("private", "42"), "hi")
        with pytest.raises(LookupError, match="渠道 telegram"):
            await service.send("telegram", "mira", AccountTarget("private", "42"), "hi")
    rpc.failure = ValueError("platform rejected target")
    with account_delivery_scope(state):
        with pytest.raises(ValueError, match="platform rejected"):
            await service.send("chat", "mira", AccountTarget("private", "42"), "hi")

    ledger = AccountDeliveryLedger(tmp_path)
    assert [
        (row.account_id, row.target_options["channel"], row.status, row.error)
        for row in ledger.list_for_role("mira")
    ] == [
        ("", "telegram", "failed", "LookupError"),
        (account_id, "chat", "failed", "ValueError"),
    ]
    assert [
        (row.account_id, row.status, row.error) for row in ledger.list_for_role("other")
    ] == [("", "failed", "LookupError")]
    assert len(rpc.calls) == 1
    assert state == {}


@pytest.mark.asyncio
async def test_account_removed_before_send_is_named_by_channel_only(
    tmp_path, monkeypatch
) -> None:
    service, accounts, rpc, _ledger, account_id = _service(tmp_path)
    account = service.channel_account("chat", "mira")
    # Listed at lookup, gone by the time the send is authorized.
    monkeypatch.setattr(accounts, "list", lambda role_id=None: [account])
    accounts.release(account_id, "live")
    with pytest.raises(LookupError, match="渠道 chat 的账号已不可用") as raised:
        await service.send("chat", "mira", AccountTarget("private", "42"), "hi")
    assert account_id not in str(raised.value)
    assert rpc.calls == []


@pytest.mark.asyncio
async def test_channel_send_uses_the_roles_account_and_keeps_plugin_snapshot(
    tmp_path,
) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.via = _VIA
    target = AccountTarget("group", "room-1", mention_ids=("member-2",))
    receipt = await service.send("chat", "mira", target, "hello")

    [(name, payload)] = rpc.calls
    assert name == "plugin.chat.account.send"
    assert payload == {
        "account_id": account_id,
        "message": "hello",
        "media": [],
        "target_kind": "group",
        "target_id": "room-1",
        "message_thread_id": None,
        "group_id": "",
        "mention_ids": ["member-2"],
    }
    assert (receipt.account_id, receipt.channel) == (account_id, "chat")
    assert receipt.via_account == _VIA
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert attempt.target_options["mention_ids"] == ["member-2"]


@pytest.mark.asyncio
async def test_images_reach_the_plugin_and_need_no_text(tmp_path) -> None:
    service, _accounts, rpc, _ledger, _account_id = _service(tmp_path)
    receipt = await service.send(
        "chat",
        "mira",
        AccountTarget("private", "42"),
        "",
        source="proactive",
        media=["D:/media/scene.png"],
    )
    [(_name, payload)] = rpc.calls
    assert (payload["message"], payload["media"]) == ("", ["D:/media/scene.png"])
    assert receipt.platform_message_id == "receipt-1"

    with pytest.raises(ValueError, match="不能都为空"):
        await service.send("chat", "mira", AccountTarget("private", "42"), " ")
    assert len(rpc.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "via",
    [
        {**_VIA, "platform_account_id": "someone-else"},
        {"prefix": "no identity"},
    ],
)
async def test_invalid_snapshot_after_send_still_returns_the_recorded_receipt(
    tmp_path, caplog, via
) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.via = via
    with caplog.at_level("ERROR", logger="shiori_sdk.accounts.models"):
        receipt = await service.send(
            "chat", "mira", AccountTarget("private", "42"), "hi"
        )

    # The platform accepted it: a plugin's bad snapshot only loses the snapshot.
    assert receipt.via_account is None
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.status, attempt.platform_message_id) == (
        "sent",
        receipt.platform_message_id,
    )
    [record] = caplog.records
    assert account_id in record.getMessage()


@pytest.mark.asyncio
async def test_channel_listing_and_targets_never_expose_account_ids(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    [listed] = service.list_channels("mira")
    assert listed["channel"] == "chat"
    assert listed["online"] is True
    assert account_id not in repr(listed)
    assert service.list_channels("other") == []

    result = await service.targets("chat", "mira", "known", "", "")
    assert result["items"] == [{"id": "42"}]
    assert rpc.calls[-1][1]["account_id"] == account_id
    with pytest.raises(LookupError, match="渠道 chat"):
        await service.targets("chat", "other", "known", "", "")


@pytest.mark.asyncio
async def test_uncertain_timeout_remains_pending(tmp_path) -> None:
    service, _accounts, rpc, _ledger, account_id = _service(tmp_path)
    rpc.failure = TimeoutError("reply lost")
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(TimeoutError):
            await service.send("chat", "mira", AccountTarget("private", "42"), "hello")
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
            await service.send("chat", "mira", AccountTarget("private", "42"), "hello")
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
            await service.send("chat", "mira", AccountTarget("private", "42"), "hello")
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
            await service.send("chat", "mira", AccountTarget("private", "42"), "hello")
    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (attempt.status, attempt.error) == ("pending", "CancelledError")
    assert state == {"sent": True}


def _bind(store: UserIdentityStore, record, user_id: str, scope, chat=None):
    """Pairs ``user_id`` through ``record``; ``chat`` defaults to its private chat."""
    code = store.create_pairing_code().code
    identity = store.pair(
        code,
        record=record,
        user_id=user_id,
        scope=scope,
        chat=chat or IdentityChat(record.id, record.plugin_id, user_id),
    )
    assert identity is not None
    return identity


def test_user_chat_is_the_remembered_private_chat_of_the_roles_account(
    tmp_path,
) -> None:
    service, accounts, _rpc, _ledger, account_id = _service(tmp_path)
    store = UserIdentityStore(tmp_path)
    other = accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="other-bot",
        config_ref="other-bot",
        token="live",
        role_id="other",
    ).record
    # An account-scoped ID of another role's account never names the user here.
    _bind(store, other, "stranger-id", "account")
    identity = _bind(
        store,
        accounts.get(account_id).record,
        "user-7",
        "platform",
        IdentityChat(account_id, "chat_bot", "dm-7"),
    )

    resolved = service.user_chat("chat", "mira")

    assert resolved.target == AccountTarget("private", "user-7")
    assert resolved.chat == identity.chat_for(account_id)


def test_user_chat_refuses_an_unbound_or_unreached_channel(tmp_path) -> None:
    service, accounts, rpc, ledger, _account_id = _service(tmp_path)
    store = UserIdentityStore(tmp_path)
    with pytest.raises(LookupError, match="没有在渠道 chat 绑定身份"):
        service.user_chat("chat", "mira")

    # Bound platform-wide through another role's account: the ID is known,
    # but the user never wrote to this role's account, so no chat is known.
    other = accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="other-bot",
        config_ref="other-bot",
        token="live",
        role_id="other",
    ).record
    _bind(store, other, "user-7", "platform")
    with pytest.raises(LookupError, match="还没有私聊过当前角色"):
        service.user_chat("chat", "mira")
    assert rpc.calls == []
    assert ledger.list_for_role("mira") == []
