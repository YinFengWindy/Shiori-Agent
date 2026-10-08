"""The TTS package owns private configuration, role lifecycle and service cleanup."""

import httpx
import pytest
from shiori_sdk.role_events import RoleDeleted
from plugins.gpt_sovits_tts.backend import plugin
from plugins.gpt_sovits_tts.backend.client import SovitsClient


async def test_setup_private_rpc_and_role_delete(context, configured, monkeypatch):
    client = SovitsClient(httpx.MockTransport(lambda _: httpx.Response(500)))
    monkeypatch.setattr(plugin, "SovitsClient", lambda: client)
    await plugin.setup(context)
    assert context.services.entries["tts"]["contract"] == "shiori.tts.v1"
    voice = await context.rpc.handlers["role.get"]({"role_id": "role"})
    assert voice["default"] is not None
    assert voice["default"]["duration"] is None
    # Saving an older reference records the duration measured from its own file.
    assert await context.rpc.handlers["role.set"](
        {"role_id": "role", "voice": voice}
    ) == {
        **voice,
        "default": {**voice["default"], "duration": 3.0},
    }
    assert context.roles.extensions.values == {}
    assert context.config.as_dict() == {}
    context.roles.values.pop("role")
    await context.events.emit(RoleDeleted("role"))
    assert configured.store.read().roles == {}
    with pytest.raises(ValueError, match="不存在"):
        await context.rpc.handlers["role.get"]({"role_id": "role"})
    await context.aclose()
    assert not context.services.entries
    assert client.http.is_closed


async def test_invalid_private_role_save_does_not_overwrite(
    context, configured, monkeypatch
):
    client = SovitsClient(httpx.MockTransport(lambda _: httpx.Response(500)))
    monkeypatch.setattr(plugin, "SovitsClient", lambda: client)
    await plugin.setup(context)
    previous = configured.store.read()
    with pytest.raises(ValueError, match="不存在"):
        await context.rpc.handlers["role.set"](
            {"role_id": "role", "voice": {"default": {"asset": "0" * 32 + ".wav"}}}
        )
    assert configured.store.read() == previous
