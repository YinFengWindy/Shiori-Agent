"""Independent memory construction and persistent vector compatibility."""

from pathlib import Path

from shiori_sdk.memory.build import (
    MemoryBuildConfig,
    MemoryPluginBuildDeps,
    MemoryPluginRuntime,
    MemoryStorage,
    MemoryStorageIncompatibleError,
)

from .config import (
    ensure_default_memory_config_file,
    load_default_memory_config,
    resolve_memory_db_path,
)
from .engine import DefaultMemoryEngine
from .semantic.store import VEC_DIM


class MemoryPlugin:
    """Builds the default engine and owns its private storage compatibility rules."""

    plugin_id = "default"

    def ensure_workspace_storage(
        self, *, config: MemoryBuildConfig, workspace: Path, storage: MemoryStorage
    ) -> list[tuple[Path, bool]]:
        """Initializes storage without changing existing user configuration."""
        ensure_default_memory_config_file(workspace=workspace, storage=storage)
        default_config = load_default_memory_config(
            workspace=workspace, storage=storage
        )
        db_path = resolve_memory_db_path(
            workspace=workspace, default_config=default_config, storage=storage
        )
        existed = db_path.exists()
        DefaultMemoryEngine.ensure_workspace_storage(
            default_config=default_config, workspace=workspace, storage=storage
        )
        return [(db_path, existed)]

    def validate_transition(
        self,
        previous: MemoryBuildConfig,
        candidate: MemoryBuildConfig,
        workspace: Path,
        storage: MemoryStorage,
    ) -> None:
        """Rejects incompatible persisted vector spaces without rewriting data."""
        path = resolve_memory_db_path(
            workspace=workspace,
            default_config=load_default_memory_config(
                workspace=workspace, storage=storage
            ),
            storage=storage,
        )
        if not path.exists():
            return
        old, new = previous.embedding, candidate.embedding
        if old.model != new.model or (old.output_dimensionality or VEC_DIM) != (
            new.output_dimensionality or VEC_DIM
        ):
            raise MemoryStorageIncompatibleError(
                "Existing memory vectors require an explicit migration before changing embedding model or dimensions"
            )

    def build(self, deps: MemoryPluginBuildDeps) -> MemoryPluginRuntime:
        """Registers allocations as they are made, then transfers a completed engine."""
        default_config = load_default_memory_config(
            workspace=deps.workspace, storage=deps.storage
        )
        engine = DefaultMemoryEngine(
            config=deps.config,
            default_config=default_config,
            workspace=deps.workspace,
            provider=deps.provider,
            light_provider=deps.light_provider,
            requester=deps.requester,
            storage=deps.storage,
            roles=deps.roles,
            skills=deps.skills,
            resources=deps.resources,
            event_publisher=deps.event_publisher,
        )
        return MemoryPluginRuntime(
            engine=engine,
            closeables=list(engine.closeables),
            admin=engine,
            resources=deps.resources.transfer(),
        )
