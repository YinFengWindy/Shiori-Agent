"""Feishu delivery stays usable when the real host avatar cache rejects contact lookup."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
import pytest
from agent.plugin_host.avatars import AvatarsCapability
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.kv import PluginKVStore
from core.channel_avatars import ChannelAvatarStore
from plugins.feishu.tests.conftest import build_harness, message_event, OPEN_ID


@pytest.fixture
async def make_harness(tmp_path) -> AsyncIterator:
    harnesses = []

    def make(**kwargs):
        harness = build_harness(tmp_path, **kwargs)
        harnesses.append(harness)
        return harness

    try:
        yield make
    finally:
        for harness in harnesses:
            await harness.channel.stop()


@pytest.fixture
def make_event():
    return message_event


async def test_without_contact_permission_messages_arrive_without_a_name(
    make_harness: Any,
    make_event: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = ChannelAvatarStore(tmp_path)
    harness = make_harness(
        profile_store=PluginKVStore(tmp_path / "profiles.json"),
        profile_ref="feishu:cli_a",
        avatars=AvatarsCapability(store, EffectScope("feishu"), "feishu"),
    )
    # 99991672: the app lacks the contact permission.
    harness.api.fail("contact", (400, 99991672))
    connection = await harness.start()

    connection.emit(make_event())
    await harness.settle()
    for _ in range(100):
        if "头像获取失败" in caplog.text:
            break
        await asyncio.sleep(0.01)
    connection.emit(make_event(message_id="om_in_2", event_id="ev_2"))
    await harness.settle()

    assert [item.content for item in harness.bus.inbound] == ["你好", "你好"]
    assert all("sender_name" not in item.metadata for item in harness.bus.inbound)
    assert "头像获取失败" in caplog.text
    # One lookup for the sender and the private chat; not retried until due.
    assert harness.api.keys().count("contact") == 1
    assert store.index().sender("feishu", OPEN_ID) is None
