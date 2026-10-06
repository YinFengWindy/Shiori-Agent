"""Real asyncio barriers prove ownership lasts beyond an abandoned caller."""

import asyncio
import json

import httpx
import pytest
from plugins.gpt_sovits_tts.backend.client import SovitsClient
from plugins.gpt_sovits_tts.backend.engine import SynthesisEngine
from plugins.gpt_sovits_tts.backend.references import References
from plugins.gpt_sovits_tts.backend.rpc import register_rpc
from plugins.gpt_sovits_tts.backend.runtime import create_runtime


def request(text="第一句", mood="Neutral"):
    return {"role_id": "role", "text": text, "mood": mood}


@pytest.mark.parametrize("owned", [True, False])
async def test_restart_recovers_owned_crash_but_refuses_foreign_inference(
    context, configured, owned
):
    engine = SynthesisEngine(
        configured.store, configured, SovitsClient(), context.background, context.roles
    )
    identity = str(configured.store.root / "runtime")
    with engine.instance.lease():
        engine.instance.begin(
            "http://127.0.0.1:12345",
            {"generation": "previous", "runtime": identity} if owned else None,
        )
    if owned:
        await engine.recover_managed(identity)
        assert not engine.instance.marker.exists()
    else:
        with pytest.raises(RuntimeError, match="切回外部服务"):
            await engine.recover_managed(identity)
        assert engine.instance.marker.exists()
    await engine.close()


async def test_old_engine_completion_keeps_same_audio_reimported_by_new_editor(
    context, configured, wav_bytes
):
    entered, finish = asyncio.Event(), asyncio.Event()
    old_references = References(configured.store)
    old_asset = configured.store.read().roles["role"].default.asset
    original_audio = old_references.path(old_asset).read_bytes()
    assert not old_references.imported

    async def respond(req):
        if req.url.path == "/tts":
            entered.set()
            await finish.wait()
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    old = SynthesisEngine(
        configured.store,
        old_references,
        SovitsClient(httpx.MockTransport(respond)),
        context.background,
        context.roles,
    )
    accepted = asyncio.create_task(old.synthesize(request()))
    await entered.wait()
    new_references = References(configured.store)
    new_references.reconcile({"role"}, sweep=True)
    new = SynthesisEngine(
        configured.store,
        new_references,
        SovitsClient(httpx.MockTransport(respond)),
        context.background,
        context.roles,
    )
    register_rpc(context, new, create_runtime(context, configured.store))

    async def import_audio(content):
        source = (
            context.workspace / "private_runtime/imports/gpt_sovits_tts-audio/a.wav"
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        return await context.rpc.handlers["reference.import"](
            {"role_id": "role", "source": str(source)}
        )

    async def save(asset):
        return await context.rpc.handlers["role.set"](
            {"role_id": "role", "voice": {"default": {"asset": asset}}}
        )

    try:
        replacement = await import_audio(wav_bytes(signal=2))
        await save(replacement["asset"])
        reimported = await import_audio(original_audio)
        finish.set()
        await accepted
        # The old generation can retire its committed identity, but not the
        # same bytes newly imported into another generation's unsaved draft.
        saved = await save(reimported["asset"])
        assert saved["default"]["asset"] == reimported["asset"]
        assert new_references.path(reimported["asset"]).read_bytes() == original_audio
        assert reimported["asset"] != old_asset
    finally:
        finish.set()
        await accepted
        await old.close()
        await new.close()


async def test_cancel_does_not_release_instance_or_reference(
    context, configured, import_reference, wav_bytes
):
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = []
    payloads = []

    async def respond(req):
        calls.append(req.url.path)
        if req.url.path == "/tts":
            payloads.append(json.loads(req.content))
            if len(calls) == 3:
                entered.set()
                await finish.wait()
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    client = SovitsClient(httpx.MockTransport(respond))
    engine = SynthesisEngine(
        configured.store, configured, client, context.background, context.roles
    )
    first = asyncio.create_task(engine.synthesize(request()))
    await entered.wait()
    old = configured.store.read().roles["role"].default.asset
    old_path = configured.path(old)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    new = import_reference(signal=2)
    configured.store.save_role("role", {"default": {"asset": new}})
    configured.collect()
    assert old_path.exists()
    second = asyncio.create_task(engine.synthesize(request("第二句")))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert calls == ["/set_gpt_weights", "/set_sovits_weights", "/tts"]
    assert engine.instance.status()["busy"] is True
    with pytest.raises(RuntimeError, match="仍在等待"):
        await engine.reconnect({"service_restarted": True})
    finish.set()
    assert (await second)["format"] == "wav"
    assert len(calls) == 6
    assert payloads[0]["ref_audio_path"] == str(old_path)
    assert payloads[1]["ref_audio_path"] == str(configured.path(new))
    assert not old_path.exists()
    await engine.close()


async def test_moods_select_different_private_references(
    context, configured, import_reference, wav_bytes
):
    happy = import_reference(signal=2)
    voice = configured.store.read().roles["role"].model_dump()
    voice["moods"] = {
        "Happy": {"asset": happy, "prompt_text": "开心参考", "prompt_lang": "zh"}
    }
    configured.store.save_role("role", voice)
    payloads = []

    def respond(req):
        if req.url.path == "/tts":
            payloads.append(json.loads(req.content))
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    client = SovitsClient(httpx.MockTransport(respond))
    engine = SynthesisEngine(
        configured.store, configured, client, context.background, context.roles
    )
    await engine.synthesize(request())
    await engine.synthesize(request(mood="Happy"))
    assert payloads[0]["ref_audio_path"] != payloads[1]["ref_audio_path"]
    assert payloads[1]["prompt_text"] == "开心参考"
    assert all("emotion" not in payload for payload in payloads)
    await engine.close()


async def test_disconnect_quarantines_across_restart_until_explicit_recovery(
    context, configured
):
    calls = []

    async def respond(req):
        calls.append(req.url.path)
        if req.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/tts": {},
                        "/set_gpt_weights": {},
                        "/set_sovits_weights": {},
                    }
                },
            )
        raise httpx.ReadError("connection lost", request=req)

    client = SovitsClient(httpx.MockTransport(respond))
    engine = SynthesisEngine(
        configured.store, configured, client, context.background, context.roles
    )
    with pytest.raises(RuntimeError, match="完成状态未知"):
        await engine.synthesize(request())
    replacement = SynthesisEngine(
        configured.store, configured, client, context.background, context.roles
    )
    assert replacement.instance.status()["recovery_required"] is True
    with pytest.raises(RuntimeError, match="状态未知"):
        await replacement.synthesize(request("不可进入"))
    assert calls == ["/set_gpt_weights"]
    with pytest.raises(ValueError, match="先重启"):
        await replacement.reconnect({})
    await replacement.reconnect({"service_restarted": True})
    assert replacement.instance.status()["recovery_required"] is False
    await replacement.close()


async def test_close_waits_for_actual_completion(context, configured, wav_bytes):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def respond(req):
        if req.url.path == "/tts":
            entered.set()
            await finish.wait()
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    client = SovitsClient(httpx.MockTransport(respond))
    engine = SynthesisEngine(
        configured.store, configured, client, context.background, context.roles
    )
    accepted = asyncio.create_task(engine.synthesize(request()))
    await entered.wait()
    closing = asyncio.create_task(engine.close())
    await asyncio.sleep(0)
    assert not closing.done() and not client.http.is_closed
    finish.set()
    await accepted
    await closing
    assert client.http.is_closed


@pytest.mark.parametrize("old_failed", [False, True])
async def test_distinct_engines_wait_for_live_owner_and_preserve_new_marker(
    context, configured, import_reference, wav_bytes, old_failed
):
    old_entered, old_finish = asyncio.Event(), asyncio.Event()
    new_entered, new_finish = asyncio.Event(), asyncio.Event()
    entered_order = []

    async def old_response(req):
        if req.url.path == "/tts":
            entered_order.append("old")
            old_entered.set()
            await old_finish.wait()
            if old_failed:
                raise httpx.ReadError("old disconnected", request=req)
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    async def new_response(req):
        if req.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/tts": {},
                        "/set_gpt_weights": {},
                        "/set_sovits_weights": {},
                    }
                },
            )
        if req.url.path == "/tts":
            entered_order.append("new")
            new_entered.set()
            await new_finish.wait()
            return httpx.Response(200, content=wav_bytes(1))
        return httpx.Response(200, json={"message": "success"})

    old = SynthesisEngine(
        configured.store,
        configured,
        SovitsClient(httpx.MockTransport(old_response)),
        context.background,
        context.roles,
    )
    new = SynthesisEngine(
        configured.store,
        References(configured.store),
        SovitsClient(httpx.MockTransport(new_response)),
        context.background,
        context.roles,
    )
    first = asyncio.create_task(old.synthesize(request()))
    await old_entered.wait()
    old_marker = old.instance.status()["instance"]
    assert new.instance.status()["busy"] is True
    assert new.instance.status()["recovery_required"] is False
    with pytest.raises(RuntimeError, match="其他活动任务"):
        await new.reconnect({"service_restarted": True})
    next_asset = import_reference(signal=3)
    unsaved_asset = import_reference(signal=4)
    configured.store.save_role("role", {"default": {"asset": next_asset}})
    second = asyncio.create_task(new.synthesize(request("替换后的请求")))
    await asyncio.sleep(0.06)
    assert entered_order == ["old"]
    old_finish.set()
    if old_failed:
        with pytest.raises(RuntimeError, match="完成状态未知"):
            await first
        with pytest.raises(RuntimeError, match="状态未知"):
            await second
        await new.reconnect({"service_restarted": True})
        second = asyncio.create_task(new.synthesize(request("重建后的请求")))
    else:
        await first
    await new_entered.wait()
    assert new.instance.status()["instance"] != old_marker
    assert new.references.path(next_asset).exists()
    # Old owner cleanup after new inference has entered cannot clear the new marker.
    await old.close()
    assert new.instance.marker.exists()
    assert new.references.path(next_asset).exists()
    assert new.references.path(unsaved_asset).exists()
    new_finish.set()
    assert (await second)["format"] == "wav"
    await new.close()
