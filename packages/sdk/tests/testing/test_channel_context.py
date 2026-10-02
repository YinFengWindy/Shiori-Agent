"""Channel setup fixtures own asynchronous avatar downloads until teardown."""

import asyncio

from shiori_sdk.testing.channel_context import FakeChannelPluginContext


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
