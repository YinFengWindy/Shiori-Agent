"""Dispatch persistent compatibility checks to the selected memory plugin."""

from pathlib import Path

from agent.config_models import Config

from bootstrap.memory_capabilities import (
    HostMemoryStorage,
    default_memory_enabled,
    memory_build_config,
)


def validate_memory_transition(
    previous: Config, candidate: Config, workspace: Path
) -> None:
    """Runs engine-owned compatibility rules before preparing a new generation."""
    if not default_memory_enabled(candidate):
        return
    from bootstrap.wiring import resolve_memory_plugin

    plugin = resolve_memory_plugin("default")
    plugin.validate_transition(
        memory_build_config(previous),
        memory_build_config(candidate),
        workspace,
        HostMemoryStorage(),
    )
