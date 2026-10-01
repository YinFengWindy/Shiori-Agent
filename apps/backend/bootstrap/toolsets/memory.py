from __future__ import annotations

from agent.tools.registry import ToolRegistry
from bootstrap.memory import build_memory_runtime
from bootstrap.toolsets.protocol import (
    ToolsetDeps,
    ToolsetProvider,
    build_registration_result,
)


class MemoryToolsetProvider(ToolsetProvider):
    def register(
        self,
        registry: ToolRegistry,
        deps: ToolsetDeps,
    ):
        before = set(registry._tools.keys())
        config = deps.config
        http_resources = deps.http_resources
        if config is None or http_resources is None:
            raise ValueError("memory toolset 缺少必要依赖")
        memory_runtime = build_memory_runtime(
            config,
            deps.workspace,
            registry,
            deps.provider,
            deps.light_provider,
            http_resources,
            event_publisher=deps.event_publisher,
        )
        return build_registration_result(
            registry=registry,
            source_name="memory",
            before=before,
            extras={"memory_runtime": memory_runtime},
        )
