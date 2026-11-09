"""Independent Fish Audio TTS/ASR registration and resource ownership."""

from shiori_sdk.core.services import EVENTS, ROLES, SERVICES, WORKSPACE
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.voice import ASR_CONTRACT, TTS_CONTRACT

from .client import FishClient
from .rpc import register_rpc
from .service import SpeechService
from .settings import VoiceStore


async def setup(ctx: PluginRuntimeContext) -> None:
    """Publish both providers without requiring a desktop-pet consumer."""
    store = VoiceStore(ctx.require(WORKSPACE))
    roles = ctx.require(ROLES)

    def reconcile(_event: RoleDeleted | None = None) -> None:
        with roles.read_scope():
            store.reconcile({role.id for role in roles.list_roles()})

    reconcile()
    ctx.require(EVENTS).on(RoleDeleted, reconcile)
    client = FishClient()
    ctx.effect("fish_audio_http", client.close)
    service = SpeechService(store, client, roles)
    register_rpc(ctx, service)
    ctx.require(SERVICES).register(
        "tts",
        contract=TTS_CONTRACT,
        label="Fish Audio",
        methods={"synthesize": service.synthesize},
    )
    ctx.require(SERVICES).register(
        "asr",
        contract=ASR_CONTRACT,
        label="Fish Audio · transcribe-1-pro",
        methods={"transcribe": service.transcribe},
    )
