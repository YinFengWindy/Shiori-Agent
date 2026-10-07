"""SenseVoice-owned private Python, offline dependency installation and CPU service."""

from pathlib import Path

from shiori_sdk.managed.paths import environment_path
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.plugin_services import ServicePluginContext

from .runtime_manifest import INSTALLED_SIZE, PYTHON_RELATIVE, REVISION, resources
from .runtime_build import build_runtime
from .runtime_environment import SCRATCH, runtime_environment
from .settings import Settings, SettingsStore


def create_runtime(ctx: ServicePluginContext, store: SettingsStore) -> ManagedRuntime:
    """Build from fixed offline packages; large files follow the chosen install root.

    Pointer, location, locks and logs stay in plugin data (``root``).
    """
    root = store.root / "runtime"
    artifacts = resources()
    installation = Installation(
        root,
        REVISION,
        artifacts,
        installed_size=INSTALLED_SIZE,
        scratch=SCRATCH,
    )

    def launch(version: Path, port: int, token: str):
        version = Path(environment_path(version))
        return (
            [
                str(version / PYTHON_RELATIVE),
                "-I",
                "-X",
                "utf8",
                str(version / "server.py"),
                str(port),
                token,
            ],
            version,
            runtime_environment(installation.install_root, version / "p"),
        )

    return ManagedRuntime(
        installation,
        OwnedService(root, ctx.processes, launch),
        ctx.background,
        lambda staging, _resources: build_runtime(
            staging, ctx, root, installation.install_root, artifacts
        ),
        lambda: store.read().connection_mode,
    )


def effective_settings(settings: Settings, runtime: ManagedRuntime) -> Settings:
    """A managed selection never falls back to the stored external endpoint."""
    if settings.connection_mode == "external":
        return settings
    return settings.model_copy(update={"url": runtime.service.require_url()})
