"""SenseVoice-owned private Python, offline dependency installation and CPU service."""

from pathlib import Path

from shiori_sdk.managed.child import private_environment
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.plugin_services import ServicePluginContext

from .runtime_manifest import CACHE_VARIABLES, OFFLINE_ENV, REVISION, resources
from .runtime_build import build_runtime
from .settings import Settings, SettingsStore


def create_runtime(ctx: ServicePluginContext, store: SettingsStore) -> ManagedRuntime:
    """Build only inside this provider's private data, using fixed offline packages."""
    root = store.root / "runtime"
    artifacts = resources()

    def launch(installation: Path, port: int, token: str):
        return (
            [
                str(installation / "python/python.exe"),
                "-I",
                "-X",
                "utf8",
                str(installation / "server.py"),
                str(port),
                token,
            ],
            installation,
            private_environment(
                root,
                installation / "python",
                cache_variables=CACHE_VARIABLES,
                overrides=OFFLINE_ENV,
            ),
        )

    return ManagedRuntime(
        Installation(root, REVISION, artifacts),
        OwnedService(root, ctx.processes, launch),
        ctx.background,
        lambda staging: build_runtime(staging, ctx, root, artifacts),
        lambda: store.read().connection_mode,
    )


def effective_settings(settings: Settings, runtime: ManagedRuntime) -> Settings:
    """A managed selection never falls back to the stored external endpoint."""
    if settings.connection_mode == "external":
        return settings
    return settings.model_copy(update={"url": runtime.service.require_url()})
