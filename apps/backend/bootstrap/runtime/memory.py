"""Dispatch persistent compatibility checks to the selected memory plugin."""

from pathlib import Path

from agent.config_models import Config
from shiori_sdk.memory.build import (
    MemoryStorageIncompatibleError as MemoryStorageIncompatibleError,
)

from bootstrap.memory_capabilities import HostMemoryStorage, memory_build_config
from bootstrap.memory_plugins import normalize_memory_engine


def validate_memory_transition(
    previous: Config, candidate: Config, workspace: Path
) -> None:
    """Runs engine-owned compatibility rules before preparing a new generation."""
    if not candidate.memory.enabled:
        return
    from bootstrap.wiring import resolve_memory_plugin

    plugin = resolve_memory_plugin(normalize_memory_engine(candidate.memory.engine))
    plugin.validate_transition(
        memory_build_config(previous),
        memory_build_config(candidate),
        workspace,
        HostMemoryStorage(),
    )
