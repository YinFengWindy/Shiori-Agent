from __future__ import annotations

from shiori_sdk.testing.processes import FakeProcesses
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.accounts import FakeAccounts
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import FakeMessageBus

import asyncio
from dataclasses import asdict
from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_runtime import (
    LOGIN_PENDING_POLL_SECONDS,
    QQAccountsRuntime,
)
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from shiori_sdk.files.json import atomic_save_json

_AVATAR = "data:image/png;base64,iVBORw0KGgo="


@pytest.fixture(autouse=True)
def _avatar_fetch(monkeypatch):
    """Keeps connecting accounts off the network; tests set the fetched avatar."""
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr("plugins.qq.backend.accounts_runtime.fetch_qq_avatar", fetch)
    return fetch


class _Socket:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.closed = False
        self.waiting = asyncio.Event()
        self.calls: list[tuple[str, dict]] = []

    async def call(self, action, params=None):
        self.calls.append((action, params or {}))
        if action == "get_login_info":
            return {"user_id": int(self.identity), "nickname": "bot"}
        if action == "get_status":
            return {"online": True}
        raise AssertionError(action)

    async def wait_closed(self):
        await self.waiting.wait()

    async def close(self):
        self.closed = True
        self.waiting.set()


@pytest.mark.asyncio
async def test_managed_qr_wait_is_normal_and_does_not_register_fake_identity(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
    runtime = QQAccountsRuntime(
        QQAccountsStore(tmp_path), accounts, processes=FakeProcesses(), http=FakeHttp()
    )
    start = AsyncMock()
    status = AsyncMock(
        return_value={
            "phase": "login_required",
            "login_phase": "waiting_qrcode",
            "qrcode": "data:image/png;base64,QR",
            "error": "",
        }
    )
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", status)
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    assert isinstance(ref, str)

    assert await runtime.start_login(ref, "mira") == {"ref": ref, "account_id": ""}
    for _ in range(50):
        if runtime._states.get(ref, ("", ""))[0] == "login_required":
            break
        await asyncio.sleep(0.01)
    assert runtime._states[ref] == ("login_required", "")
    assert accounts.records == {}
    assert not runtime._store.path.exists()
    assert (await runtime.managed_status(ref))["login"]["qrcode"].startswith(
        "data:image"
    )
    start.assert_awaited_once_with(ref, "")

    stop = AsyncMock()
    monkeypatch.setattr(runtime._managed, "stop", stop)
    await runtime.stop_login(ref, "mira")
    stop.assert_awaited_once_with(ref)
    assert runtime._configs[ref].auto_connect is False
    await runtime.cancel_login(ref, "mira")
    assert ref not in runtime._configs
    assert not runtime._managed._files.account_dir(ref).exists()
    await runtime.stop()


@pytest.mark.asyncio
async def test_temporary_login_operations_reject_another_role(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    runtime = QQAccountsRuntime(
        QQAccountsStore(tmp_path),
        FakeAccounts("qq", id_factory=lambda value: f"qq-{value}"),
        processes=FakeProcesses(),
        http=FakeHttp(),
    )
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    assert isinstance(ref, str)

    for operation in (runtime.start_login, runtime.stop_login, runtime.cancel_login):
        with pytest.raises(ValueError, match="另一个角色"):
            await operation(ref, "other")

    assert runtime._configs[ref].auto_connect is False
    assert ref not in runtime._tasks
    assert not runtime._store.path.exists()
    await runtime.cancel_login("missing", "other")
    await runtime.cancel_login(ref, "mira")
    assert ref not in runtime._configs


@pytest.mark.asyncio
async def test_managed_scan_registers_only_after_verified_onebot_identity(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
    runtime = QQAccountsRuntime(
        store, accounts, processes=FakeProcesses(), http=FakeHttp()
    )
    start = AsyncMock()
    login_status = AsyncMock(
        side_effect=[
            {
                "phase": "login_required",
                "qrcode": "data:image/png;base64,QR",
                "error": "",
            },
            {"phase": "online", "qrcode": "", "error": ""},
        ]
    )
    socket = _Socket("101")
    socket.open = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", login_status)
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    assert isinstance(ref, str)

    assert (await runtime.start_login(ref, "mira"))["account_id"] == ""
    for _ in range(50):
        if runtime._states.get(ref, ("", ""))[0] == "login_required":
            break
        await asyncio.sleep(0.01)
    assert accounts.records == {}
    socket.open.assert_not_awaited()
    for _ in range(150):
        if (
            "qq-101" in accounts.records
            and accounts.records["qq-101"].connection == "online"
        ):
            break
        await asyncio.sleep(0.02)

    assert login_status.await_count == 2
    socket.open.assert_awaited_once()
    assert socket.calls[:2] == [("get_login_info", {}), ("get_status", {})]
    assert accounts.records["qq-101"].connection == "online"
    assert accounts.records["qq-101"].record.config_ref == ref
    assert store.load()[ref].expected_uin == "101"
    assert store.load()[ref].verified is True
    login_status.side_effect = None
    login_status.return_value = {"phase": "online", "qrcode": "", "error": ""}
    assert (await runtime.managed_status(ref))["account_id"] == "qq-101"
    with pytest.raises(ValueError, match="另一个角色"):
        await runtime.cancel_login(ref, "other")
    await runtime.cancel_login(ref, "mira")
    assert store.load()[ref].expected_uin == "101"
    await runtime.stop()


@pytest.mark.asyncio
async def test_existing_managed_session_connects_without_qr(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
    runtime = QQAccountsRuntime(
        store, accounts, processes=FakeProcesses(), http=FakeHttp()
    )
    start = AsyncMock()
    login_status = AsyncMock(
        return_value={"phase": "online", "qrcode": "", "error": ""}
    )
    socket = _Socket("101")
    socket.open = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", login_status)
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    assert isinstance(ref, str)

    await runtime.start_login(ref, "mira")
    for _ in range(50):
        if (
            "qq-101" in accounts.records
            and accounts.records["qq-101"].connection == "online"
        ):
            break
        await asyncio.sleep(0.01)
    assert accounts.records["qq-101"].connection == "online"
    assert login_status.await_count == 1
    assert store.load()[ref].verified is True
    assert (await runtime.managed_status(ref))["login"]["qrcode"] == ""
    await runtime.stop()


@pytest.mark.asyncio
async def test_restart_removes_unverified_record_and_orphan_instance(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    abandoned = QQConnectionConfig(
        "aabb", "ws://127.0.0.1:3001", "token", role_id="mira"
    )
    atomic_save_json(store.path, {"version": 1, "accounts": [asdict(abandoned)]})
    runtime = QQAccountsRuntime(
        store,
        FakeAccounts("qq", id_factory=lambda value: f"qq-{value}"),
        processes=FakeProcesses(),
        http=FakeHttp(),
    )
    orphan = runtime._managed._files.account_dir("ccdd")
    orphan.mkdir(parents=True)
    saved_temp = runtime._managed._files.account_dir("aabb")
    saved_temp.mkdir(parents=True)

    await runtime.load()
    assert store.load() == {}
    assert not saved_temp.exists()
    assert not orphan.exists()


@pytest.mark.asyncio
async def test_managed_logout_keeps_identity_but_clears_login(monkeypatch, tmp_path):
    store = QQAccountsStore(tmp_path)
    config = QQConnectionConfig(
        "known",
        "ws://127.0.0.1:3001",
        "secret",
        expected_uin="101",
        verified=True,
        role_id="mira",
    )
    store.save({"known": config})
    accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
    runtime = QQAccountsRuntime(
        store, accounts, processes=FakeProcesses(), http=FakeHttp()
    )
    runtime.register_saved()
    stop = AsyncMock()
    logout = AsyncMock()
    monkeypatch.setattr(runtime._managed, "stop", stop)
    monkeypatch.setattr(runtime._managed, "logout", logout)

    await runtime.logout("qq-101")
    stop.assert_awaited_once_with("known")
    logout.assert_awaited_once_with("known")
    assert store.load()["known"].expected_uin == "101"
    assert store.load()["known"].auto_connect is False
    assert accounts.records["qq-101"].connection == "login_required"


@pytest.mark.asyncio
async def test_connected_avatar_is_stored_reregistered_and_kept_on_failed_refresh(
    monkeypatch, tmp_path, _avatar_fetch
):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            "known": QQConnectionConfig(
                "known",
                "ws://127.0.0.1:3001",
                "secret",
                expected_uin="101",
                verified=True,
                role_id="mira",
            )
        }
    )

    async def connect(fetched: str | None) -> FakeAccounts:
        _avatar_fetch.return_value = fetched
        _avatar_fetch.reset_mock()
        accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
        runtime = QQAccountsRuntime(
            store, accounts, processes=FakeProcesses(), http=FakeHttp()
        )
        await runtime.load()
        socket = _Socket("101")
        socket.open = AsyncMock()
        monkeypatch.setattr(runtime._managed, "start", AsyncMock())
        monkeypatch.setattr(
            runtime._managed,
            "login_status",
            AsyncMock(return_value={"phase": "online", "qrcode": "", "error": ""}),
        )
        monkeypatch.setattr(
            "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
        )
        runtime._schedule("known")
        for _ in range(100):
            if _avatar_fetch.await_count:
                break
            await asyncio.sleep(0.01)
        await asyncio.gather(*runtime._avatar_tasks.values())
        _avatar_fetch.assert_awaited_once_with("101", requester=runtime._http)
        await runtime.stop()
        return accounts

    await connect(_AVATAR)
    assert store.load()["known"].avatar == _AVATAR

    restarted = await connect(None)
    assert restarted.avatars["101"] == _AVATAR
    assert store.load()["known"].avatar == _AVATAR


@pytest.mark.asyncio
async def test_disconnect_cancels_an_avatar_fetch_in_flight(
    monkeypatch, tmp_path, _avatar_fetch
):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            "known": QQConnectionConfig(
                "known",
                "ws://127.0.0.1:3001",
                "secret",
                expected_uin="101",
                verified=True,
                role_id="mira",
            )
        }
    )
    fetching = asyncio.Event()

    async def slow_fetch(_uin, **_kwargs):
        fetching.set()
        await asyncio.Event().wait()

    _avatar_fetch.side_effect = slow_fetch
    runtime = QQAccountsRuntime(
        store,
        FakeAccounts("qq", id_factory=lambda value: f"qq-{value}"),
        processes=FakeProcesses(),
        http=FakeHttp(),
    )
    await runtime.load()
    socket = _Socket("101")
    socket.open = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", AsyncMock())
    monkeypatch.setattr(runtime._managed, "stop", AsyncMock())
    monkeypatch.setattr(
        runtime._managed,
        "login_status",
        AsyncMock(return_value={"phase": "online", "qrcode": "", "error": ""}),
    )
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    runtime._schedule("known")
    await asyncio.wait_for(fetching.wait(), timeout=1)
    fetch_task = runtime._avatar_tasks["known"]

    await runtime.disconnect("qq-101")

    assert fetch_task.cancelled()
    assert "known" not in runtime._avatar_tasks
    await runtime.stop()


@pytest.mark.asyncio
async def test_pending_login_is_rechecked_quickly_without_flapping(
    monkeypatch, tmp_path
):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            "known": QQConnectionConfig(
                "known",
                "ws://127.0.0.1:3001",
                "secret",
                expected_uin="101",
                verified=True,
                role_id="mira",
            )
        }
    )
    accounts = FakeAccounts("qq", id_factory=lambda value: f"qq-{value}")
    runtime = QQAccountsRuntime(
        store, accounts, processes=FakeProcesses(), http=FakeHttp()
    )
    runtime.register_saved()
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            runtime._stopping = True
        await real_sleep(0)

    monkeypatch.setattr("plugins.qq.backend.accounts_runtime.asyncio.sleep", sleep)
    monkeypatch.setattr(runtime._managed, "start", AsyncMock())
    monkeypatch.setattr(
        runtime._managed,
        "login_status",
        AsyncMock(return_value={"phase": "login_required", "qrcode": "", "error": ""}),
    )

    await runtime._reconnect("known")

    assert sleeps == [LOGIN_PENDING_POLL_SECONDS] * 3
    assert LOGIN_PENDING_POLL_SECONDS <= 1.0
    assert [fields["connection"] for _, fields in accounts.reports] == [
        "connecting"
    ] + ["login_required"] * 3


@pytest.mark.asyncio
async def test_account_added_after_handover_resume_receives_private_messages(
    monkeypatch, tmp_path
):
    """A runtime handover starts the channel paused, then resumes it; an account
    verified afterwards through the add flow must not start its intake paused.
    """
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    runtime = QQAccountsRuntime(
        QQAccountsStore(tmp_path),
        FakeAccounts("qq", id_factory=lambda value: f"qq-{value}"),
        processes=FakeProcesses(),
        http=FakeHttp(),
    )
    monkeypatch.setattr(runtime._managed, "start", AsyncMock())
    monkeypatch.setattr(
        runtime._managed,
        "login_status",
        AsyncMock(return_value={"phase": "online", "qrcode": "", "error": ""}),
    )
    socket = _Socket("101")
    socket.open = AsyncMock()
    callbacks = []

    def open_socket(_uri, _token, _timeout, on_event):
        callbacks.append(on_event)
        return socket

    monkeypatch.setattr("plugins.qq.backend.accounts_runtime.OneBotSocket", open_socket)
    bus, hub = FakeMessageBus(), FakeChannelHub()
    routed = hub.offered
    ctx = fake_channel_context(
        tmp_path / "uploads", bus=bus, channel_hub=hub, intake_paused=True
    )
    await runtime.start(ctx)
    runtime.resume_intake()

    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    assert isinstance(ref, str)
    await runtime.start_login(ref, "mira")
    for _ in range(50):
        if runtime._states.get(ref, ("", ""))[0] == "online":
            break
        await asyncio.sleep(0.01)
    assert runtime._states[ref] == ("online", "")

    [on_event] = callbacks
    await on_event(
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": 101,
            "user_id": 902,
            "message_id": 1,
            "raw_message": "你好",
        }
    )

    assert [message.content for message in routed] == ["你好"]
    [published] = bus.inbound
    assert published.metadata["account_id"] == "qq-101"
    await runtime.stop()
