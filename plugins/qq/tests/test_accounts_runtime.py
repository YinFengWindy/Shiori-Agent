from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.qq.backend.accounts_runtime import QQAccountsRuntime
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from plugins.qq.backend.onebot import OneBotAuthError, OneBotError


class _Accounts:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}
        self.states: dict[str, str] = {}
        self.reports: list[tuple[str, str, str]] = []

    def register(self, *, platform, platform_account_id, config_ref, display_name=None):
        account_id = f"qq-{platform_account_id}"
        for row in self.rows.values():
            if (
                row.platform_account_id == platform_account_id
                and row.config_ref != config_ref
            ):
                raise ValueError("duplicate physical account")
        row = SimpleNamespace(
            id=account_id,
            platform_account_id=platform_account_id,
            config_ref=config_ref,
            display_name=display_name,
        )
        self.rows[account_id] = row
        return SimpleNamespace(record=row)

    def report(self, account_id, *, connection, capabilities=frozenset(), error=""):
        self.states[account_id] = connection
        self.reports.append((account_id, connection, error))
        return SimpleNamespace(record=self.rows[account_id])


class _Socket:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.closed = False
        self.waiting = asyncio.Event()
        self.calls: list[tuple[str, dict]] = []
        self.online = True

    async def call(self, action, params=None):
        self.calls.append((action, params or {}))
        if action == "get_status":
            return {"online": self.online}
        if action == "get_login_info":
            return {"user_id": int(self.identity), "nickname": "bot"}
        if action == "get_friend_list":
            return [{"user_id": 901, "nickname": f"friend-{self.identity}"}]
        if action == "get_group_list":
            return [{"group_id": 777, "group_name": "group"}]
        if action == "get_group_member_list":
            return [{"user_id": 902, "card": "member"}]
        if action in {"send_private_msg", "send_group_msg"}:
            return {"message_id": int(self.identity)}
        raise AssertionError(action)

    async def wait_closed(self):
        await self.waiting.wait()

    async def close(self):
        self.closed = True
        self.waiting.set()


class _FailingSocket(_Socket):
    async def wait_closed(self):
        raise OneBotError("malformed NapCat frame")


class _Bus:
    def __init__(self) -> None:
        self.inbound = []

    def subscribe_outbound(self, *_args):
        pass

    def unsubscribe_outbound(self, *_args):
        pass

    async def publish_inbound(self, message):
        self.inbound.append(message)


@pytest.mark.asyncio
async def test_two_accounts_keep_identity_discovery_send_and_events_isolated(
    monkeypatch,
    tmp_path,
):
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    sockets = {"101": _Socket("101"), "202": _Socket("202")}

    async def verified(_ref, config):
        identity = "101" if config.ws_uri.endswith("3001") else "202"
        return sockets[identity], {
            "user_id": int(identity),
            "nickname": f"bot-{identity}",
        }

    monkeypatch.setattr(runtime, "_verified_socket", verified)
    bus = _Bus()
    push_tool = SimpleNamespace(
        register_channel=lambda *_a, **_k: None,
        unregister_channel=lambda *_a, **_k: None,
    )
    await runtime.start(
        SimpleNamespace(
            bus=bus, push_tool=push_tool, intake_paused=False, channel_hub=None
        )
    )
    first = await runtime.save_draft(
        {"ws_uri": "ws://localhost:3001", "ws_token": "one"}
    )
    second = await runtime.save_draft(
        {"ws_uri": "ws://localhost:3002", "ws_token": "two"}
    )
    assert accounts.rows == {}
    assert runtime._sockets == {}

    a = (await runtime.connect_saved(first["ref"]))["account_id"]
    b = (await runtime.connect_saved(second["ref"]))["account_id"]
    assert a != b
    assert accounts.states == {a: "online", b: "online"}
    assert (await runtime.discover(a, "friends"))["items"] == [
        {"id": "901", "name": "friend-101"}
    ]
    assert (await runtime.discover(b, "groups"))["items"] == [
        {"id": "777", "name": "group"}
    ]
    assert (await runtime.discover(a, "members", "777"))["complete"] is True
    assert (await runtime.send_target(b, "group", "777", "hello")) == {
        "message_id": "202"
    }
    assert (
        await runtime._send_with_metadata("901", "account B only", {"account_id": b})
        == "202"
    )
    assert ("send_group_msg", {"group_id": 777, "message": "hello"}) in sockets[
        "202"
    ].calls
    assert not any(action == "send_group_msg" for action, _ in sockets["101"].calls)
    assert (
        "send_private_msg",
        {"user_id": 901, "message": "account B only"},
    ) in sockets["202"].calls

    await runtime._on_event(
        first["ref"],
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": 101,
            "user_id": 901,
            "message_id": 11,
            "raw_message": "hi",
        },
    )
    await runtime._on_event(
        second["ref"],
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 202,
            "user_id": 902,
            "group_id": 777,
            "message_id": 12,
            "raw_message": "[CQ:at,qq=202] hello",
        },
    )
    assert [(msg.metadata["account_id"], msg.chat_id) for msg in bus.inbound] == [
        (a, "901"),
        (b, "gqq:777"),
    ]

    sockets["101"].online = False
    with pytest.raises(OneBotAuthError, match="尚未登录"):
        await runtime.discover(a, "friends")
    assert accounts.states[a] == "login_required"
    assert (await runtime.send_target(b, "private", "901", "still online")) == {
        "message_id": "202"
    }
    assert accounts.states[b] == "online"

    await runtime.disconnect(a)
    assert accounts.states[a] == "offline"
    assert accounts.states[b] == "online"
    assert not sockets["202"].closed
    with pytest.raises(OneBotError, match="明确指定账号"):
        await runtime._send_legacy("901", "must not use account B")
    await runtime.stop()


@pytest.mark.asyncio
async def test_identity_mismatch_preserves_old_socket_and_saved_identity(
    monkeypatch, tmp_path
):
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    old = _Socket("101")
    candidate = _Socket("202")

    async def verified(_ref, config):
        if config.ws_uri.endswith("3001"):
            return old, {"user_id": 101, "nickname": "first"}
        if config.expected_uin != "202":
            await candidate.close()
            raise OneBotError("NapCat 登录的是 202，账号记录要求 101")
        return candidate, {"user_id": 202, "nickname": "second"}

    monkeypatch.setattr(runtime, "_verified_socket", verified)
    first = await runtime.save_draft({"ws_uri": "ws://localhost:3001"})
    account_id = (await runtime.connect_saved(first["ref"]))["account_id"]
    await runtime.save_draft(
        {"account_id": account_id, "ws_uri": "ws://localhost:3002"}
    )
    assert not old.closed
    with pytest.raises(OneBotError, match="账号记录要求 101"):
        await runtime.connect_saved(first["ref"])
    assert not old.closed
    assert runtime._configs[first["ref"]].expected_uin == "101"
    await runtime.stop()


@pytest.mark.asyncio
async def test_failed_pending_connection_keeps_active_credentials_after_restart(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, _Accounts())
    active = _Socket("101")

    async def verified(_ref, config):
        if config.ws_uri.endswith("3002"):
            raise OneBotError("replacement credentials rejected")
        return active, {"user_id": 101, "nickname": "bot"}

    monkeypatch.setattr(runtime, "_verified_socket", verified)
    ref = (
        await runtime.save_draft(
            {
                "ws_uri": "ws://localhost:3001",
                "ws_token": "working-token",
            }
        )
    )["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    await runtime.save_draft(
        {
            "account_id": account_id,
            "ws_uri": "ws://localhost:3002",
            "ws_token": "bad-token",
        }
    )
    saved = store.load()[ref]
    assert (saved.ws_uri, saved.ws_token, saved.auto_connect) == (
        "ws://localhost:3001",
        "working-token",
        True,
    )
    assert saved.pending is not None
    assert (saved.pending.ws_uri, saved.pending.ws_token) == (
        "ws://localhost:3002",
        "bad-token",
    )
    assert runtime.settings(ref=ref)["account"]["ws_uri"] == "ws://localhost:3002"
    with pytest.raises(OneBotError, match="replacement credentials rejected"):
        await runtime.connect_saved(ref)
    assert runtime._sockets[ref] is active
    assert not active.closed
    assert store.load()[ref] == saved
    await runtime.stop()

    restarted = QQAccountsRuntime(store, _Accounts())
    restored = _Socket("101")
    used = []

    async def restore(_ref, config):
        used.append((config.ws_uri, config.ws_token))
        return restored, {"user_id": 101, "nickname": "bot"}

    monkeypatch.setattr(restarted, "_verified_socket", restore)
    bus = _Bus()
    push_tool = SimpleNamespace(
        register_channel=lambda *_a, **_k: None,
        unregister_channel=lambda *_a, **_k: None,
    )
    await restarted.start(
        SimpleNamespace(
            bus=bus,
            push_tool=push_tool,
            intake_paused=False,
            channel_hub=None,
        )
    )
    for _ in range(20):
        if restarted._sockets.get(ref) is restored:
            break
        await asyncio.sleep(0)
    assert used == [("ws://localhost:3001", "working-token")]
    assert store.load()[ref].pending == saved.pending
    await restarted.stop()


@pytest.mark.asyncio
async def test_registration_rejection_keeps_previous_config_and_live_socket(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    original = _Socket("101")
    candidate = _Socket("101")

    async def verified(_ref, config):
        socket = original if config.ws_uri.endswith("3001") else candidate
        return socket, {"user_id": 101, "nickname": "same QQ"}

    monkeypatch.setattr(runtime, "_verified_socket", verified)
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    await runtime.save_draft(
        {"account_id": account_id, "ws_uri": "ws://localhost:3002"}
    )
    before = store.load()[ref]
    monkeypatch.setattr(
        accounts,
        "register",
        MagicMock(
            side_effect=ValueError("platform account belongs to another configuration")
        ),
    )

    with pytest.raises(ValueError, match="another configuration"):
        await runtime.connect_saved(ref)
    assert store.load()[ref] == before
    assert runtime._configs[ref] == before
    assert runtime._sockets[ref] is original
    assert not original.closed
    assert candidate.closed
    # A restart still sees the prior verified identity and can register it.
    assert (
        QQAccountsRuntime(store, _Accounts()).settings(ref=ref)["account"][
            "expected_uin"
        ]
        == "101"
    )
    await runtime.stop()


@pytest.mark.asyncio
async def test_rejected_first_registration_does_not_mark_draft_verified(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    candidate = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            return_value=(
                candidate,
                {"user_id": 101, "nickname": "QQ"},
            )
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    monkeypatch.setattr(
        accounts,
        "register",
        MagicMock(side_effect=ValueError("identity already registered")),
    )
    with pytest.raises(ValueError, match="already registered"):
        await runtime.connect_saved(ref)
    assert store.load()[ref].verified is False
    assert candidate.closed
    QQAccountsRuntime(store, accounts)


@pytest.mark.asyncio
async def test_legacy_number_is_not_registered_before_real_login(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="secret",
        timeout_seconds=5,
    )
    accounts = _Accounts()
    QQAccountsRuntime(store, accounts)
    assert accounts.rows == {}


@pytest.mark.asyncio
async def test_verified_socket_checks_login_uin_and_online_state(monkeypatch, tmp_path):
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), _Accounts())
    socket = _Socket("202")
    socket.open = AsyncMock()
    socket.call = AsyncMock(
        side_effect=[
            {"user_id": 202, "nickname": "other"},
            {"online": True},
        ]
    )
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    config = QQConnectionConfig(
        "old", "ws://localhost:3001", "secret", expected_uin="101"
    )
    with pytest.raises(OneBotError, match="账号记录要求 101"):
        await runtime._verified_socket("old", config)
    assert socket.closed
    socket.call.assert_awaited_once_with("get_login_info")


@pytest.mark.asyncio
async def test_saved_account_reports_auth_failure_without_claiming_online(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    config = QQConnectionConfig(
        "known",
        "ws://localhost:3001",
        "secret",
        expected_uin="101",
        verified=True,
    )
    store.save({"known": config})
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(side_effect=OneBotAuthError("QQ 尚未登录")),
    )
    bus = _Bus()
    push_tool = SimpleNamespace(
        register_channel=lambda *_a, **_k: None,
        unregister_channel=lambda *_a, **_k: None,
    )
    await runtime.start(
        SimpleNamespace(
            bus=bus,
            push_tool=push_tool,
            intake_paused=False,
            channel_hub=None,
        )
    )
    for _ in range(20):
        if accounts.states.get("qq-101") == "login_required":
            break
        await asyncio.sleep(0)
    assert accounts.states["qq-101"] == "login_required"
    await runtime.stop()


@pytest.mark.asyncio
async def test_socket_alive_logout_blocks_actions_and_updates_account_status(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.STATUS_CHECK_INTERVAL_SECONDS", 0.01
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    bus = _Bus()
    push_tool = SimpleNamespace(
        register_channel=lambda *_a, **_k: None,
        unregister_channel=lambda *_a, **_k: None,
    )
    await runtime.start(
        SimpleNamespace(
            bus=bus,
            push_tool=push_tool,
            intake_paused=False,
            channel_hub=None,
        )
    )
    socket = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            side_effect=[
                (socket, {"user_id": 101, "nickname": "bot"}),
                OneBotAuthError("QQ 尚未登录"),
            ]
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    socket.online = False
    with pytest.raises(OneBotAuthError, match="尚未登录"):
        await runtime.send_target(account_id, "private", "901", "blocked")
    assert accounts.states[account_id] == "login_required"
    assert not any(action == "send_private_msg" for action, _ in socket.calls)
    await runtime._on_socket_event(
        ref,
        socket,
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": 101,
            "user_id": 901,
            "raw_message": "must not arrive",
        },
    )
    assert bus.inbound == []
    with pytest.raises(OneBotError, match="不在线"):
        await runtime.discover(account_id, "friends")
    for _ in range(50):
        if socket.closed:
            break
        await asyncio.sleep(0.01)
    assert socket.closed
    assert any(state == "login_required" for _, state, _ in accounts.reports)
    await runtime.stop()


@pytest.mark.asyncio
async def test_periodic_status_check_detects_logout_without_an_account_action(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.STATUS_CHECK_INTERVAL_SECONDS", 0.01
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    socket = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            side_effect=[
                (socket, {"user_id": 101, "nickname": "bot"}),
                OneBotAuthError("QQ 尚未登录"),
            ]
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    socket.online = False
    for _ in range(50):
        if socket.closed:
            break
        await asyncio.sleep(0.01)
    assert socket.closed
    assert any(
        row_id == account_id and state == "login_required"
        for row_id, state, _ in accounts.reports
    )
    await runtime.stop()


@pytest.mark.asyncio
async def test_socket_alive_identity_switch_cannot_send_as_the_old_account(
    monkeypatch, tmp_path
):
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    socket = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            return_value=(
                socket,
                {"user_id": 101, "nickname": "bot"},
            )
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    socket.identity = "202"
    with pytest.raises(OneBotError, match="身份与账号记录不匹配"):
        await runtime.send_target(account_id, "private", "901", "blocked")
    assert accounts.states[account_id] == "error"
    assert not any(action == "send_private_msg" for action, _ in socket.calls)
    await runtime.stop()


@pytest.mark.asyncio
async def test_manual_connection_reader_failure_reports_error_and_reconnects(
    monkeypatch, tmp_path
):
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    failed = _FailingSocket("101")
    replacement = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            side_effect=[
                (failed, {"user_id": 101, "nickname": "bot"}),
                (replacement, {"user_id": 101, "nickname": "bot"}),
            ]
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]
    for _ in range(30):
        if runtime._sockets.get(ref) is replacement:
            break
        await asyncio.sleep(0)
    assert failed.closed
    assert (account_id, "error", "malformed NapCat frame") in accounts.reports
    assert runtime._sockets[ref] is replacement
    assert accounts.states[account_id] == "online"
    await runtime.stop()


@pytest.mark.asyncio
async def test_migrated_account_becomes_verified_only_after_login(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="secret",
        timeout_seconds=5,
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    assert accounts.rows == {}
    socket = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            return_value=(
                socket,
                {"user_id": 101, "nickname": "verified bot"},
            )
        ),
    )
    bus = _Bus()
    push_tool = SimpleNamespace(
        register_channel=lambda *_a, **_k: None,
        unregister_channel=lambda *_a, **_k: None,
    )
    await runtime.start(
        SimpleNamespace(
            bus=bus,
            push_tool=push_tool,
            intake_paused=False,
            channel_hub=None,
        )
    )
    for _ in range(20):
        if accounts.states.get("qq-101") == "online":
            break
        await asyncio.sleep(0)
    assert accounts.states["qq-101"] == "online"
    assert store.load()["legacy"].verified is True
    await runtime.stop()


@pytest.mark.asyncio
async def test_platform_failure_and_missing_receipt_are_not_reported_as_success(
    monkeypatch,
    tmp_path,
):
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), _Accounts())
    socket = _Socket("101")
    monkeypatch.setattr(
        runtime,
        "_verified_socket",
        AsyncMock(
            return_value=(
                socket,
                {"user_id": 101, "nickname": "bot"},
            )
        ),
    )
    ref = (await runtime.save_draft({"ws_uri": "ws://localhost:3001"}))["ref"]
    account_id = (await runtime.connect_saved(ref))["account_id"]

    async def missing_receipt(action, _params=None):
        if action == "get_status":
            return {"online": True}
        if action == "get_login_info":
            return {"user_id": 101}
        return {}

    socket.call = AsyncMock(side_effect=missing_receipt)
    with pytest.raises(ValueError, match="消息回执"):
        await runtime.send_target(account_id, "private", "901", "hello")
    with pytest.raises(ValueError, match="目标 ID"):
        await runtime.send_target(account_id, "group", "gqq:777", "hello")
    await runtime.stop()
