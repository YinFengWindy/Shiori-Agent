"""Private configuration and standalone WAV test endpoints."""

import base64

from shiori_sdk.core.services import RPC, WORKSPACE
from shiori_sdk.files.staging import staged_import_file
from shiori_sdk.rpc import Concurrency
from shiori_sdk.runtime import PluginRuntimeContext

from .client import MAX_AUDIO_BYTES
from .service import SpeechService
from .settings import RoleVoice


def register_rpc(ctx: PluginRuntimeContext, service: SpeechService) -> None:
    """Expose Fish-owned settings and voices, never role draft extensions."""
    store = service.store

    async def settings_get(_params: dict[str, object]):
        return store.public_settings()

    async def settings_set(params: dict[str, object]):
        return store.save_settings(params)

    async def role_get(params: dict[str, object]):
        with service.roles.read_scope():
            role_id = service.require_role(params)
            return store.read().roles.get(role_id, RoleVoice()).model_dump()

    async def role_set(params: dict[str, object]):
        with service.roles.read_scope():
            role_id = service.require_role(params)
            voice = RoleVoice.model_validate(params.get("voice"))
            return store.save_role(role_id, voice).model_dump()

    async def transcribe_file(params: dict[str, object]):
        source = params.get("source")
        if not isinstance(source, str):
            raise ValueError("请选择 WAV 文件")
        path = staged_import_file(
            ctx.require(WORKSPACE),
            "fish_audio-audio",
            source,
            suffix=".wav",
            max_bytes=MAX_AUDIO_BYTES,
        )
        try:
            return await service.transcribe(
                {
                    "audio_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
                    "format": "wav",
                }
            )
        finally:
            path.unlink(missing_ok=True)

    ctx.require(RPC).register(
        "settings.get", settings_get, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register("settings.set", settings_set)
    ctx.require(RPC).register("role.get", role_get, concurrency=Concurrency.READ_ONLY)
    ctx.require(RPC).register("role.set", role_set)
    ctx.require(RPC).register(
        "transcribe_file", transcribe_file, concurrency=Concurrency.INTEGRATION
    )
