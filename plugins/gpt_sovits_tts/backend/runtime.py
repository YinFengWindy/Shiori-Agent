"""Own the independent GPT-SoVITS environment and its explicit endpoint selection."""

from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.plugin_services import ServicePluginContext
from .runtime_build import build_runtime
from .runtime_launch import launch_runtime
from .runtime_manifest import ARTIFACTS, INSTALLED_SIZE, REQUIRED_FILES, REVISION
from .settings import Settings, VoiceStore


def create_runtime(ctx: ServicePluginContext, store: VoiceStore) -> ManagedRuntime:
    """Wire provider-owned policy to generic installation and native process ownership."""
    root = store.root / "runtime"
    return ManagedRuntime(
        Installation(root, REVISION, ARTIFACTS, installed_size=INSTALLED_SIZE),
        OwnedService(
            root,
            ctx.processes,
            lambda path, port, token: launch_runtime(path, port, token, root),
        ),
        ctx.background,
        lambda staging: build_runtime(staging, ctx, root),
        lambda: store.read().settings.connection_mode,
    )


def effective_settings(settings: Settings, runtime: ManagedRuntime) -> Settings:
    """Managed calls use only the owned endpoint and this package's fixed weights."""
    if settings.connection_mode == "external":
        return settings
    return settings.model_copy(
        update={
            "url": runtime.service.require_url(),
            "gpt_weights": REQUIRED_FILES[3],
            "sovits_weights": REQUIRED_FILES[4],
        }
    )
