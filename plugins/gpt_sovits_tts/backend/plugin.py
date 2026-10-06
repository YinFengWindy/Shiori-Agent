"""Public TTS registration, role reconciliation, and provider resource ownership."""

from typing import Protocol

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.services import ServiceProviderContext
from shiori_sdk.voice import TTS_CONTRACT

from .client import SovitsClient
from .engine import SynthesisEngine
from .references import References
from .rpc import register_rpc
from .settings import VoiceStore


class Context(ServicePluginContext, ServiceProviderContext, Protocol):
    """Compose SDK context capabilities, independent of all consuming plugins."""


async def setup(ctx: Context) -> None:
    """Reconcile private data and publish one serialized v2ProPlus service."""
    store = VoiceStore(ctx.workspace)
    references = References(store)

    def reconcile(_event: RoleDeleted | None = None) -> None:
        with ctx.roles.read_scope():
            references.reconcile(
                {role.id for role in ctx.roles.list_roles()}, sweep=_event is None
            )

    reconcile()
    ctx.events.on(RoleDeleted, reconcile)
    engine = SynthesisEngine(
        store, references, SovitsClient(), ctx.background, ctx.roles
    )
    ctx.effect("gpt_sovits_engine", engine.close)
    register_rpc(ctx, engine)
    ctx.services.register(
        "tts",
        contract=TTS_CONTRACT,
        label="GPT-SoVITS · v2ProPlus",
        methods={"synthesize": engine.synthesize},
        metadata={"version": "v2ProPlus"},
    )
