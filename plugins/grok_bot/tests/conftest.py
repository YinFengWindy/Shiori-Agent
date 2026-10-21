"""SDK-only fixtures; all remote transport is explicit and deterministic."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import FakeMessageBus
from shiori_sdk.testing.storage import FakeKV
from shiori_sdk.testing.events import FakeEvents

from plugins.grok_bot.backend.config import ConnectionConfig
from plugins.grok_bot.backend.connection import GrokConnection


@pytest.fixture
def config() -> ConnectionConfig:
    return ConnectionConfig(
        connection_id=uuid4().hex,
        peer_id=uuid4().hex,
        role_id="mira",
        webhook_url="https://example.test/routine",
        webhook_key="test-webhook-secret",
        callback_token="test-callback-token-" + uuid4().hex,
    )


@dataclass
class Harness:
    """A real loopback listener, with a fake remote Grok webhook and SDK host."""

    connection: GrokConnection
    bus: FakeMessageBus
    hub: FakeChannelHub
    events: FakeEvents
    requests: list[dict[str, object]] = field(default_factory=list)


@pytest.fixture
async def harness(tmp_path: Path, config: ConnectionConfig):
    requests: list[dict[str, object]] = []

    def handle(request: httpx.Request):
        assert request.headers["Authorization"] == f"Bearer {config.webhook_key}"
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"success": True, "runUuid": "run-is-not-a-message-id"}
        )

    connection = GrokConnection(
        config,
        FakeKV(),
        tmp_path / "data",
        Path(__file__).resolve().parents[1] / "client.ps1",
        config_changed=lambda value: None,
        status_changed=lambda state, error: None,
        transport=httpx.MockTransport(handle),
    )
    bus, hub = FakeMessageBus(), FakeChannelHub(role_id=config.role_id)
    events = FakeEvents()
    await connection.start(
        fake_channel_context(tmp_path, bus=bus, channel_hub=hub, event_bus=events)
    )
    try:
        yield Harness(connection, bus, hub, events, requests)
    finally:
        await connection.stop()
