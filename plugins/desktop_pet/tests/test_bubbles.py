"""Dismissal is a scoped public RPC event with drain-safe admission."""

import pytest
from shiori_sdk.testing.memory_context import FakeRpc
from shiori_sdk.rpc import Concurrency
from plugins.desktop_pet.backend.bubbles import register_bubble_rpc


@pytest.mark.asyncio
async def test_dismiss_publishes_to_pet_background():
    rpc = FakeRpc()
    register_bubble_rpc(rpc)
    assert await rpc.handlers["bubble.dismiss"]({}) == {"ok": True}
    assert rpc.events == [("bubble.dismissed", {})]
    assert rpc.concurrency["bubble.dismiss"] is Concurrency.READ_ONLY
    assert rpc.admission_exempt["bubble.dismiss"] is True
