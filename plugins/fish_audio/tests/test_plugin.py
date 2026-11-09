"""Real plugin setup publishes both contracts with only SDK fakes."""

import base64
import httpx
import pytest
from shiori_sdk.role_events import RoleDeleted

from plugins.fish_audio.backend import plugin
from plugins.fish_audio.backend.client import FishClient
from plugins.fish_audio.backend.settings import VoiceStore


async def test_independent_service_registration_role_selection_and_unload(
    context, tmp_path, audio, monkeypatch
):
    import json

    requests = []

    def serve(request):
        if request.url.path == "/v1/tts":
            requests.append(json.loads(request.content))
            return httpx.Response(200, content=b"ID3audio")
        return httpx.Response(200, json={"text": "你好"})

    client = FishClient(httpx.MockTransport(serve))
    monkeypatch.setattr(plugin, "FishClient", lambda: client)
    await plugin.setup(context)
    rpc = context.fake_rpc.handlers
    await rpc["settings.set"]({"api_key": "key", "tts_model": "s2.1-pro-free"})
    for name, language in (("alice", "ja"), ("bob", "en")):
        await rpc["role.set"](
            {
                "role_id": name,
                "voice": {"reference_id": name, "speed": 1.0, "language": language},
            }
        )
    for name in ("bob", "alice"):
        result = await context.fake_services.methods["tts", "synthesize"](
            {"text": "你好", "role_id": name, "mood": "开心"}
        )
        assert result == {
            "audio_base64": base64.b64encode(b"ID3audio").decode(),
            "format": "mp3",
        }
    assert [(request["reference_id"], request["language"]) for request in requests] == [
        ("bob", "en"),
        ("alice", "ja"),
    ]
    # The whole private role document round-trips; resetting one role to auto
    # removes the API override without changing the other role's language.
    alice = await rpc["role.get"]({"role_id": "alice"})
    assert alice["language"] == "ja"
    await rpc["role.set"]({"role_id": "alice", "voice": {**alice, "language": "auto"}})
    await context.fake_services.methods["tts", "synthesize"](
        {"text": "今日は November 9。", "role_id": "alice", "mood": ""}
    )
    assert requests[-1]["text"] == "今日は November 9。"
    assert "language" not in requests[-1]
    assert (await rpc["role.get"]({"role_id": "bob"}))["language"] == "en"
    assert await context.fake_services.methods["asr", "transcribe"](
        {"audio_base64": base64.b64encode(audio).decode(), "format": "wav"}
    ) == {"text": "你好"}
    assert context.fake_roles.extensions.values == {}
    context.fake_roles.values.pop("alice")
    await context.fake_events.emit(RoleDeleted("alice"))
    assert set(VoiceStore(tmp_path).read().roles) == {"bob"}
    with pytest.raises(ValueError, match="不存在"):
        await rpc["role.set"]({"role_id": "alice", "voice": {"reference_id": "ghost"}})
    await context.aclose()
    assert not context.fake_services.entries
    assert client.http.is_closed
