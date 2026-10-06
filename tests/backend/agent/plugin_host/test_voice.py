"""Scoped speech registration, plugin isolation and generation ownership."""

import io
import json
import wave
import pytest
from agent.config import load_config_data
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.kernel import HostServices, PluginKernel
from agent.plugin_host.voice import VoiceProviderRegistry, ScopedVoiceCapability
from bootstrap.tools import _resolve_plugin_dirs
from bus.event_bus import EventBus
from desktop_bridge.voice.voice_service import VoiceService
from shiori_sdk.voice import VoiceProviderInfo, VoiceServiceError


class Provider:
    info = VoiceProviderInfo("sample", "Sample")


def test_duplicate_registration_is_rejected_without_overwriting_owner():
    registry = VoiceProviderRegistry()
    first = Provider()
    scope = EffectScope("first")
    registry.register("asr", first, scope)
    with pytest.raises(ValueError, match="重复"):
        registry.register("asr", Provider(), EffectScope("second"))
    assert registry.asr("sample") is first


async def test_old_disposer_cannot_unregister_a_new_instance():
    registry = VoiceProviderRegistry()
    old_scope = EffectScope("plugin")
    registry.register("tts", Provider(), old_scope)
    old_dispose = old_scope._effects[0].dispose
    await old_scope.dispose_all()
    current = Provider()
    registry.register("tts", current, EffectScope("plugin"))
    old_dispose()
    assert registry.tts("sample") is current
    with pytest.raises(RuntimeError, match="已处置"):
        ScopedVoiceCapability(registry, old_scope).register_tts(Provider())


async def test_migrated_cloud_plugins_are_discovered_called_and_independently_unloaded(
    monkeypatch,
    tmp_path,
):
    config = load_config_data(
        {
            "voice": {
                "enabled": True,
                "asr": {"enabled": True, "secret_id": "id", "secret_key": "key"},
                "tts": {"enabled": True, "api_key": "tts-key", "volume": 2.5},
            }
        }
    )
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                {"Response": {"Result": "你好", "RequestId": "asr-1"}}
            ).encode()

        def __iter__(self):
            yield b'data: {"data":{"audio":"0102"}}\n'

    def request(req, *, timeout):
        requests.append((req.full_url, json.loads(req.data)))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", request)
    kernel = PluginKernel(
        _resolve_plugin_dirs(tmp_path),
        external_plugin_dirs=[tmp_path / "plugins"],
        services=HostServices(
            event_bus=EventBus(),
            workspace=tmp_path,
            plugin_configs=config.plugins,
            raw_plugin_configs=config.raw_plugin_configs,
        ),
    )
    try:
        assert await kernel.load("tencent_asr")
        assert await kernel.load("minimax_tts")
        service = VoiceService(config.voice, kernel.voice)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\0" * 32000)
        assert service.transcribe(buf.getvalue()) == "你好"
        assert (
            service.synthesize("回复", voice_id="role", speed=1, emotion="happy")
            == b"\1\2"
        )
        assert requests[1][1]["voice_setting"]["vol"] == 2.5
        assert {item["plugin_id"] for item in service.describe_providers()} == {
            "tencent_asr",
            "minimax_tts",
        }
        await kernel.unload("tencent_asr")
        with pytest.raises(VoiceServiceError, match="ASR provider 不可用"):
            service.transcribe(buf.getvalue())
        assert service.synthesize("仍可朗读", voice_id="role", speed=1) == b"\1\2"
        await kernel.unload("minimax_tts")
        with pytest.raises(VoiceServiceError, match="TTS provider 不可用"):
            service.synthesize("停用", voice_id="role", speed=1)
    finally:
        await kernel.terminate_all()
