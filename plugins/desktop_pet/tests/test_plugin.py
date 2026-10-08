"""Setup registers pet-owned capabilities using only SDK test support."""

import pytest
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.rpc import Concurrency
from plugins.desktop_pet.backend.plugin import setup


@pytest.mark.asyncio
async def test_setup_registers_scoped_tools_rpc_and_role_participant(tmp_path):
    ctx = FakeServiceContext("desktop_pet", tmp_path)
    await setup(ctx.as_capability())
    assert "pet_action" in ctx.tools.tools
    assert set(ctx.rpc.handlers) == {
        "binding.get",
        "pets.list",
        "pets.import",
        "pets.remove",
        "pets.select",
        "bubble.dismiss",
        "voice.preferences.get",
        "voice.preferences.set",
        "voice.context.get",
        "bilibili.login.start",
        "bilibili.login.poll",
        "bilibili.account.status",
        "bilibili.account.logout",
    }
    assert ctx.rpc.concurrency["binding.get"] is Concurrency.READ_ONLY
    assert ctx.rpc.concurrency["pets.import"] is Concurrency.MUTATION
    assert ctx.rpc.admission_exempt["bubble.dismiss"]
    assert await ctx.rpc.handlers["binding.get"]({}) == {"binding": None}
    assert "desktop_pet" in ctx.roles.extensions.participants
    await ctx.aclose()
    assert not ctx.roles.extensions.participants
    assert not ctx.tools.tools
    assert not ctx.rpc.handlers
