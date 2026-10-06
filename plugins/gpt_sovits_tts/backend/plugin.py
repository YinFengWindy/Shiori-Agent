"""Public TTS registration, role reconciliation, and provider resource ownership."""

from typing import Protocol

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.services import ServiceProviderContext
from shiori_sdk.voice import TTS_CONTRACT
from shiori_sdk.managed.rpc import register_runtime_rpc

from .client import SovitsClient
from .engine import SynthesisEngine
from .references import References
from .rpc import register_rpc
from .settings import VoiceStore
from .runtime import create_runtime, effective_settings
from .runtime_manifest import ARCHIVE


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
    runtime = create_runtime(ctx, store)

    def managed_identity():
        if store.read().settings.connection_mode == "managed" and runtime.service.token:
            return {
                "generation": runtime.service.token,
                "runtime": str(runtime.service.root),
            }
        return None

    engine = SynthesisEngine(
        store,
        references,
        SovitsClient(),
        ctx.background,
        ctx.roles,
        lambda: effective_settings(store.read().settings, runtime),
        managed_identity,
    )
    runtime.service.on_stopped = engine.managed_stopped
    runtime.service.before_start = lambda: engine.recover_managed(
        str(runtime.service.root)
    )
    ctx.effect("gpt_sovits_engine", engine.close)
    register_runtime_rpc(
        ctx,
        runtime,
        namespace="gpt_sovits_tts-runtime",
        import_suffix=(".7z", ".zip"),
        import_asset=ARCHIVE,
    )
    register_rpc(ctx, engine, runtime)
    if runtime.mode() == "managed" and runtime.status()["installed"]:
        runtime.submit("start")
    ctx.services.register(
        "tts",
        contract=TTS_CONTRACT,
        label="GPT-SoVITS · v2ProPlus",
        methods={"synthesize": engine.synthesize},
        metadata={"version": "v2ProPlus"},
    )
