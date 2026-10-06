"""Independent ASR service and its private configuration/file-test RPCs."""

import base64
from typing import Protocol

from shiori_sdk.files.audio import pcm_wav_duration
from shiori_sdk.files.staging import staged_import_file
from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency
from shiori_sdk.services import ServiceProviderContext
from shiori_sdk.voice import ASR_CONTRACT

from .client import SenseVoiceClient
from .settings import SettingsStore


class Context(ServicePluginContext, ServiceProviderContext, Protocol):
    """Compose existing SDK services without depending on another plugin."""


async def setup(ctx: Context) -> None:
    """Publish the public ASR contract and private settings/test endpoints."""
    store = SettingsStore(ctx.workspace)
    client = SenseVoiceClient()
    ctx.effect("sensevoice_http", client.close)

    async def get(_params: dict[str, object]):
        return store.read().model_dump()

    async def save(params: dict[str, object]):
        return store.write(params).model_dump()

    async def health(_params: dict[str, object]):
        return await client.health(store.read())

    async def transcribe(params: dict[str, object]):
        if params.get("format") != "wav" or not isinstance(
            params.get("audio_base64"), str
        ):
            raise ValueError("SenseVoice 需要 WAV 录音")
        audio = base64.b64decode(str(params["audio_base64"]), validate=True)
        if len(audio) > 32 * 1024 * 1024:
            raise ValueError("录音超过 32MB")
        pcm_wav_duration(audio)
        return await client.transcribe(store.read(), audio)

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
