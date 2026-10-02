from __future__ import annotations


import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.testing.accounts import FakeAccounts
from shiori_sdk.testing.storage import FakeKV
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_services import FakeMessageBus
from shiori_sdk.testing.events import FakeEvents
from shiori_sdk.messages import InboundMessage
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.accounts import QQBotAccountStore
from plugins.qqbot.backend.channel import QQBotChannel


@pytest.fixture
def connected_gateways(monkeypatch: pytest.MonkeyPatch) -> dict[str, QQBotChannel]:
    """Expose fake gateways while retaining each child's real lifecycle and intake."""
    gateways: dict[str, QQBotChannel] = {}

    async def gateway(self: QQBotChannel) -> None:
        gateways[self._app_id] = self
        self._report_status("online")

    monkeypatch.setattr(QQBotChannel, "_gateway_loop", gateway)
    monkeypatch.setattr(
        QQBotChannel, "_get_access_token", AsyncMock(return_value="test-token")
    )
    monkeypatch.setattr(
        QQBotChannel,
        "_api_request",
        AsyncMock(return_value={"url": "wss://gateway.invalid"}),
    )
    return gateways


@pytest.mark.asyncio
@pytest.mark.parametrize("initially_paused", [True, False], ids=["paused", "running"])
@pytest.mark.parametrize("reconnect", [False, True], ids=["new", "reconnect"])
async def test_connected_applications_inherit_current_intake_state(
    tmp_path: Path,
    connected_gateways: dict[str, QQBotChannel],
    initially_paused: bool,
    reconnect: bool,
    setup_context,
) -> None:
    store = QQBotAccountStore(FakeKV())
    account = {"app_id": "200", "client_secret": "secret", "role_id": "mira"}
    if reconnect:
        store.save(account)
    manager = QQBotAccountsChannel(setup_context(), store, ())
    bus = FakeMessageBus()
    events = FakeEvents()
    runtime = fake_channel_context(
        tmp_path / "attachments",
        bus=bus,
        event_bus=events,
        intake_paused=initially_paused,
    )
    await manager.start(runtime)
    try:
        # A settings handover changes admission after the start context was saved.
        if initially_paused:
            manager.resume_intake()
        else:
            manager.pause_intake()
        await manager.save_and_connect(account)
        channel = connected_gateways["200"]
        await channel._handle_dispatch(
            "C2C_MESSAGE_CREATE",
            {"id": "first", "author": {"user_openid": "openid"}, "content": "hello"},
        )
        assert bus.inbound_size == (1 if initially_paused else 0)
        # Composite state must not mutate the context shared by the host.
        assert runtime.intake_paused is initially_paused
        if not initially_paused:
            manager.resume_intake()
        message = await asyncio.wait_for(bus.consume_inbound(), timeout=1)
        assert isinstance(message, InboundMessage)
        assert (message.sender, message.chat_id, message.content) == (
            "openid",
            "c2c:200:openid",
            "hello",
        )

        # The connected child also follows later pauses and replays queued input.
        manager.pause_intake()
        await channel._handle_dispatch(
            "C2C_MESSAGE_CREATE",
            {"id": "second", "author": {"user_openid": "openid"}, "content": "queued"},
        )
        assert bus.inbound_size == 0
        manager.resume_intake()
        replayed = await asyncio.wait_for(bus.consume_inbound(), timeout=1)
        assert isinstance(replayed, InboundMessage)
        assert replayed.content == "queued"
        assert replayed.metadata["account_id"] == "200"
        assert bus.inbound_size == 0
    finally:
        await manager.stop()
    assert events._subscriptions == []


@pytest.mark.asyncio
async def test_one_public_channel_starts_isolated_application_gateways(
    tmp_path, monkeypatch, setup_context
):
    store = QQBotAccountStore(FakeKV())
    # Without an owner role the host refuses the application.
    store.save({"app_id": "100", "client_secret": "unowned-secret"})
    store.save(
        {
            "app_id": "200",
            "client_secret": "second-secret",
            "role_id": "other",
            "connected": True,
            "targets": [],
        }
    )
    manager = QQBotAccountsChannel(setup_context(), store, ())
    started = []

    async def start(self, ctx, *, public_hooks=True):
        started.append((self._app_id, public_hooks))

    async def stop(self):
        pass

    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)
    await manager.start(fake_channel_context(tmp_path))
    try:
        # The unowned application is not registered, so it is not served.
        assert started == [("200", False)]
        assert list(manager._channels) == ["200"]
        assert manager._channels["200"]._client_secret == "second-secret"
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_connected_avatar_is_stored_reregistered_and_kept_on_failed_refresh(
    tmp_path, monkeypatch, avatar_fetch, setup_context
):
    avatar = "data:image/png;base64,iVBORw0KGgo="
    store = QQBotAccountStore(FakeKV())
    store.save({"app_id": "200", "client_secret": "secret", "role_id": "mira"})

    async def start(self, ctx, *, public_hooks=True):
        pass

    async def stop(self):
        pass

    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)

    async def connect(fetched: str | None) -> FakeAccounts:
        avatar_fetch.return_value = fetched
        context = setup_context()
        accounts = context.accounts
        manager = QQBotAccountsChannel(context, store, ())
        await manager.start(fake_channel_context(tmp_path))
        await asyncio.gather(*manager._avatar_tasks.values())
        await manager.stop()
        return accounts

    fetched = await connect(avatar)
    assert store.get("200")["avatar"] == avatar
    assert fetched.avatars["200"] == avatar

    restarted = await connect(None)
    assert restarted.avatars["200"] == avatar
    assert store.get("200")["avatar"] == avatar
