"""Checks persistent vector compatibility before preparing a memory version."""

from pathlib import Path
import importlib.util

from agent.config_models import Config


class MemoryStorageIncompatibleError(ValueError):
    """A requested vector space cannot read the existing persistent index."""

    code = "memory_storage_incompatible"

    def to_details(self):
        """Provides a non-secret remediation code for settings error reporting."""
        return {"code": self.code, "reason": "embedding_migration_required"}


def validate_memory_transition(
    previous: Config, candidate: Config, workspace: Path
) -> None:
    """Rejects incompatible vector spaces without silently rebuilding stored data."""
    if (
        not candidate.memory.enabled
        or (candidate.memory.engine or "default") != "default"
    ):
        return
    config_path = Path(__file__).resolve().parents[3] / "plugins" / "default_memory" / "backend" / "config.py"
    spec = importlib.util.spec_from_file_location("akasic_default_memory_config", config_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {config_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    load_default_memory_config = module.load_default_memory_config
    resolve_memory_db_path = module.resolve_memory_db_path
    from memory2.store import VEC_DIM

    path = resolve_memory_db_path(
        workspace=workspace, default_config=load_default_memory_config()
    )
    if not path.exists():
        return
    old = previous.memory.embedding
    new = candidate.memory.embedding
    if old.model != new.model or (old.output_dimensionality or VEC_DIM) != (
        new.output_dimensionality or VEC_DIM
    ):
        raise MemoryStorageIncompatibleError(
            "Existing memory vectors require an explicit migration before changing embedding model or dimensions"
        )
