from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.tools.registry import ToolRegistry


@pytest.fixture
def stub_core_runtime():
    """Builds a CoreRuntime-shaped stub carrying every field the bridge reads."""

    def build(**overrides) -> SimpleNamespace:
        runtime = SimpleNamespace(
            session_manager=None,
            loop=None,
            event_bus=None,
            provider=None,
            config=None,
            tools=ToolRegistry(),
            push_tool=None,
            scheduler=None,
            presence=None,
            relationship_runtime=None,
            memory_optimizer=None,
            role_runtime_registry=None,
            memory_runtime=SimpleNamespace(engine=None),
            plugin_manager=None,
        )
        for name, value in overrides.items():
            setattr(runtime, name, value)
        return runtime

    return build
