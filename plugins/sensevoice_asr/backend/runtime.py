"""SenseVoice-owned private Python, offline dependency installation and CPU service."""

from pathlib import Path

from shiori_sdk.managed.paths import environment_path
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.plugin_services import ServicePluginContext

from .runtime_manifest import INSTALLED_SIZE, PYTHON_RELATIVE, REVISION, resources
from .runtime_build import build_runtime
from .runtime_environment import runtime_environment
from .settings import Settings, SettingsStore


def create_runtime(ctx: ServicePluginContext, store: SettingsStore) -> ManagedRuntime:
    """Build only inside this provider's private data, using fixed offline packages."""
    root = store.root / "runtime"
    artifacts = resources()

    def launch(installation: Path, port: int, token: str):
        installation = Path(environment_path(installation))
        return (
            [
                str(installation / PYTHON_RELATIVE),
                "-I",
                "-X",
                "utf8",
                str(installation / "server.py"),
                str(port),
                token,
            ],
            installation,
            runtime_environment(root, installation / "p"),
        )

    return ManagedRuntime(
        Installation(root, REVISION, artifacts, installed_size=INSTALLED_SIZE),
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
