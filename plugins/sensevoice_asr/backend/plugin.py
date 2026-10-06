"""Independent ASR service and its private configuration/file-test RPCs."""

import base64
import asyncio
from typing import Protocol

from shiori_sdk.files.audio import pcm_wav_duration
from shiori_sdk.files.staging import staged_import_file
from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency
from shiori_sdk.services import ServiceProviderContext
from shiori_sdk.voice import ASR_CONTRACT
from shiori_sdk.managed.rpc import register_runtime_rpc

from .client import SenseVoiceClient
from .settings import SettingsStore
from .runtime import create_runtime, effective_settings


class Context(ServicePluginContext, ServiceProviderContext, Protocol):
    """Compose existing SDK services without depending on another plugin."""


async def setup(ctx: Context) -> None:
    """Publish the public ASR contract and private settings/test endpoints."""
    store = SettingsStore(ctx.workspace)
    client = SenseVoiceClient()
    transcription = asyncio.Lock()
    ctx.effect("sensevoice_http", client.close)
    runtime = create_runtime(ctx, store)
    register_runtime_rpc(
        ctx, runtime, namespace="sensevoice_asr-runtime", import_suffix=".zip"
    )
    if runtime.mode() == "managed" and runtime.status()["installed"]:
        runtime.submit("start")

    def settings():
        return effective_settings(store.read(), runtime)

    async def get(_params: dict[str, object]):
        return store.read().model_dump()

    async def save(params: dict[str, object]):
        if runtime.status()["busy"] or transcription.locked():
            raise RuntimeError("请等待环境操作结束后再保存连接设置")
        previous = store.read().connection_mode
        result = store.write(params)
        if previous != result.connection_mode:
            await runtime.stop()
            if result.connection_mode == "managed" and runtime.status()["installed"]:
                runtime.submit("start")
        return result.model_dump()

    async def health(_params: dict[str, object]):
        return await client.health(settings())

    async def transcribe(params: dict[str, object]):
        if params.get("format") != "wav" or not isinstance(
            params.get("audio_base64"), str
        ):
            raise ValueError("SenseVoice 需要 WAV 录音")
        audio = base64.b64decode(str(params["audio_base64"]), validate=True)
        if len(audio) > 32 * 1024 * 1024:
            raise ValueError("录音超过 32MB")
        pcm_wav_duration(audio)
        async with transcription:
            return await client.transcribe(settings(), audio)

    async def test_file(params: dict[str, object]):
        path = staged_import_file(
            ctx.workspace,
            "sensevoice_asr-audio",
            str(params.get("source", "")),
            suffix=".wav",
            max_bytes=32 * 1024 * 1024,
        )
        try:
            return await transcribe(
                {
                    "audio_base64": base64.b64encode(path.read_bytes()).decode(),
                    "format": "wav",
                }
            )
        finally:
            path.unlink(missing_ok=True)

    ctx.rpc.register("settings.get", get, concurrency=Concurrency.READ_ONLY)
    ctx.rpc.register("settings.set", save)
    ctx.rpc.register("health", health, concurrency=Concurrency.READ_ONLY)
    ctx.rpc.register("transcribe_file", test_file, concurrency=Concurrency.INTEGRATION)
    ctx.services.register(
        "asr",
        contract=ASR_CONTRACT,
        label="SenseVoiceSmall · CPU",
        methods={"transcribe": transcribe},
        metadata={"device": "cpu", "model": "SenseVoiceSmall"},
    )
