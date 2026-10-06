"""Dynamic publication is instance-owned and does not expose private plugin RPCs."""

import asyncio
import pytest
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.services import PluginServiceRegistry
from shiori_sdk.rpc import PluginRpcError


async def echo(payload):
    return {"value": payload["value"]}


async def test_registry_uses_exact_contract_and_registered_methods_only():
    registry = PluginServiceRegistry()
    scope = EffectScope("provider")
    registry.register(
        "provider",
        "echo",
        contract="sample.v1",
        label="Echo",
        methods={"run": echo},
        metadata={"nested": {"value": 1}},
        scope=scope,
    )
    result = registry.list("sample.v1")
    metadata = result[0]["metadata"]
    assert isinstance(metadata, dict)
    metadata["nested"]["value"] = 9
    assert registry.list("other.v1") == []
    fresh = registry.list("sample.v1")[0]["metadata"]
    assert isinstance(fresh, dict)
    assert fresh["nested"]["value"] == 1
    assert await registry.call(
        "provider", "echo", "run", {"value": "ok"}, caller_active=lambda: True
    ) == {"value": "ok"}
    with pytest.raises(PluginRpcError, match="未公开"):
        await registry.call(
            "provider", "echo", "private", {}, caller_active=lambda: True
        )


async def test_scope_retires_inflight_result_and_old_dispose_preserves_new_instance():
    registry = PluginServiceRegistry()
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed(_payload):
        started.set()
        await finish.wait()
        return {"ok": True}

    old = EffectScope("provider")
    registry.register(
        "provider",
        "echo",
        contract="sample.v1",
        label="Echo",
        methods={"run": delayed},
        metadata=None,
        scope=old,
    )
    disposer = old._effects[0].dispose
    task = asyncio.create_task(
        registry.call("provider", "echo", "run", {}, caller_active=lambda: True)
    )
    await started.wait()
    await old.dispose_all()
    registry.register(
        "provider",
        "echo",
        contract="sample.v1",
        label="New",
        methods={"run": echo},
        metadata=None,
        scope=EffectScope("provider"),
    )
    disposer()
    finish.set()
    with pytest.raises(PluginRpcError, match="停用"):
        await task
    assert registry.list("sample.v1")[0]["label"] == "New"


async def test_neutral_provider_setup_discovers_and_calls_without_dependency_ids(
    tmp_path,
):
    from agent.plugin_host.kernel import HostServices, PluginKernel
    from bus.event_bus import EventBus
    from desktop_bridge.plugin_requests import DesktopPluginRequestHandler

    for plugin_id, capabilities, code in [
        ("consumer", [], "async def setup(ctx):\n    pass\n"),
        (
            "neutral",
            ["services"],
            "from shiori_sdk.voice import ASR_CONTRACT, TTS_CONTRACT\nasync def transcribe(payload):\n    return {'text': payload['audio_base64']}\nasync def synthesize(payload):\n    return {'audio_base64': payload['text'], 'format': 'wav'}\nasync def setup(ctx):\n    ctx.services.register('recognition', contract=ASR_CONTRACT, label='Neutral ASR', methods={'transcribe': transcribe})\n    ctx.services.register('synthesis', contract=TTS_CONTRACT, label='Neutral TTS', methods={'synthesize': synthesize})\n",
        ),
    ]:
        package = tmp_path / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {plugin_id}\ncapabilities: {capabilities}\n", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(code, encoding="utf-8")
    kernel = PluginKernel([tmp_path], services=HostServices(event_bus=EventBus()))
    router = DesktopPluginRequestHandler(kernel.rpc)
    try:
        await kernel.load_all()
        opened = await router.handle(
            "plugins.communication.open",
            {"plugin_id": "consumer", "owner": "real-owner"},
        )
        assert opened is not None
        caller = {"plugin_id": "consumer", "owner": "real-owner", **opened}
        listing = await router.handle(
            "plugins.communication.services.list",
            {**caller, "contract": "shiori.asr.v1"},
        )
        assert listing["services"][0]["service_id"] == "recognition"
        recognized = await router.handle(
            "plugins.communication.services.call",
            {
                **caller,
                "service": {"plugin_id": "neutral", "service_id": "recognition"},
                "name": "transcribe",
                "payload": {"audio_base64": "utterance", "format": "wav"},
            },
        )
        assert recognized == {"text": "utterance"}
        synthesized = await router.handle(
            "plugins.communication.services.call",
            {
                **caller,
                "service": {"plugin_id": "neutral", "service_id": "synthesis"},
                "name": "synthesize",
                "payload": {
                    "text": recognized["text"],
                    "role_id": "role",
                    "mood": "Happy",
                },
            },
        )
        assert synthesized == {"audio_base64": "utterance", "format": "wav"}
        await kernel.unload("neutral")
        assert await router.handle(
            "plugins.communication.services.list",
            {**caller, "contract": "shiori.asr.v1"},
        ) == {"services": []}
        with pytest.raises(PluginRpcError, match="不可用"):
            await router.handle(
                "plugins.communication.services.call",
                {
                    **caller,
                    "service": {"plugin_id": "neutral", "service_id": "recognition"},
                    "name": "transcribe",
                    "payload": {},
                },
            )
    finally:
        await kernel.terminate_all()
