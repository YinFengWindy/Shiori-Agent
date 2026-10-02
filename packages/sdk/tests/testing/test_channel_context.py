"""Channel setup fixtures own asynchronous avatar downloads until teardown."""

import asyncio

from shiori_sdk.channels import ChannelContext
from shiori_sdk.testing.channel_context import (
    FakeChannelPluginContext,
    fake_channel_context,
)
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_intake import FakeChannelIntake
from shiori_sdk.testing.channel_services import FakeMessageBus


async def test_close_cancels_pending_platform_avatar_fetch(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "id: example\nchannels: []\n", encoding="utf-8"
    )
    context = FakeChannelPluginContext("example", tmp_path)
    started = asyncio.Event()

    async def fetch() -> bytes:
        started.set()
        await asyncio.Event().wait()
        return b"unreachable"

    task = context.as_capability().avatars.refresh("sender", "example", "1", fetch)
    await started.wait()
    await context.aclose()
    assert task is not None and task.cancelled()
    assert context.avatars.tasks == set()


def test_channel_plugin_context_maps_platform_account_ids(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        "id: example\nchannels: []\n", encoding="utf-8"
    )
    context = FakeChannelPluginContext(
        "example", tmp_path, account_ids=lambda value: f"account-{value}"
    )

    snapshot = context.accounts.register(
        platform="example", platform_account_id="7", config_ref="r", role_id="mira"
    )

    assert snapshot.record.id == "account-7"


async def _no_send(chat_id: str, text: str) -> str | None:
    return None


async def test_fake_channel_context_builds_a_start_context_from_sdk_fakes(tmp_path):
    bus, hub = FakeMessageBus(), FakeChannelHub(allowed=False)
    context = fake_channel_context(
        tmp_path / "uploads",
        bus=bus,
        channel_hub=hub,
        bot_commands=[("help", "帮助")],
        intake_paused=True,
    )

    assert isinstance(context, ChannelContext)
    assert context.bus is bus and context.channel_hub is hub
    assert context.bot_commands == [("help", "帮助")] and context.intake_paused
    assert context.attachment_store.create_path("a_", ".txt").parent == (
        tmp_path / "uploads"
    )
    assert isinstance(
        context.intake_factory(bus.publish_inbound, _no_send), FakeChannelIntake
    )
    # Omitted services are fresh fakes; the default hub admits.
    defaults = fake_channel_context(tmp_path)
    assert isinstance(defaults.channel_hub, FakeChannelHub)
    assert defaults.channel_hub.allowed is True
    assert defaults.interrupt_controller is None
