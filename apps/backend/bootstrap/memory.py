from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent.config_models import Config
from agent.provider import LLMProvider
from agent.skills import SkillsLoader
from agent.tools.meta import register_memory_meta_tools
from agent.tools.registry import ToolRegistry
from core.memory.markdown import build_markdown_memory_runtime
from core.memory.plugin import (
    DisabledMemoryEngine,
    MemoryPluginBuildDeps,
    MemoryPluginRuntime,
)
from core.memory.runtime import MemoryRuntime
from core.net.http import SharedHttpResources
from core.roles import RoleStore

from bootstrap.memory_capabilities import (
    HostMemoryRoles,
    HostMemoryStorage,
    memory_build_config,
)
from bootstrap.memory_plugins import normalize_memory_engine
from bootstrap.runtime.construction import MemoryBuildResources, track_build_closeables

if TYPE_CHECKING:
    from bus.event_bus import EventBus


# 统一插件构造入口，运行时与管理工具复用同一套路由。
def _build_memory_plugin_runtime(
    *,
    config: Config,
    workspace: Path,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    http_resources: SharedHttpResources,
    roles: RoleStore,
    event_publisher: "EventBus | None" = None,
) -> MemoryPluginRuntime:
    from bootstrap.wiring import resolve_memory_plugin

    engine_name = normalize_memory_engine(config.memory.engine)
    plugin = resolve_memory_plugin(engine_name)
    return plugin.build(
        MemoryPluginBuildDeps(
            config=memory_build_config(config),
            workspace=workspace,
            provider=provider,
            light_provider=light_provider,
            requester=http_resources.external_default,
            event_publisher=event_publisher,
            storage=HostMemoryStorage(),
            roles=HostMemoryRoles(roles),
            skills=lambda: [
                skill["name"]
                for skill in SkillsLoader(workspace).list_skills(
                    filter_unavailable=False
                )
            ],
            resources=MemoryBuildResources(),
        )
    )


def _memory_plugin_enabled(config: Config) -> bool:
    return bool(config.memory.enabled)


def ensure_memory_plugin_storage(
    config: Config,
    workspace: Path,
) -> list[tuple[Path, bool]]:
    if not _memory_plugin_enabled(config):
        return []
    engine_name = normalize_memory_engine(config.memory.engine)
    from bootstrap.wiring import resolve_memory_plugin

    plugin = resolve_memory_plugin(engine_name)
    return plugin.ensure_workspace_storage(
        config=memory_build_config(config),
        workspace=workspace,
        storage=HostMemoryStorage(),
    )


def build_memory_runtime(
    config: Config,
    workspace: Path,
    tools: ToolRegistry,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    http_resources: SharedHttpResources,
    event_publisher: "EventBus | None" = None,
    runtime_roles: RoleStore | None = None,
) -> MemoryRuntime:
    # 1. markdown 是默认记忆层，任何 engine 都共用。
    markdown = build_markdown_memory_runtime(
        workspace=workspace,
        provider=provider,
        model=config.model,
        keep_count=_memory_keep_count(config.memory_window),
        event_bus=event_publisher,
        recent_context_provider=light_provider or provider,
        recent_context_model=config.light_model or config.model,
    )

    closeables: list[object] = []
    resources = []
    if _memory_plugin_enabled(config):
        plugin_runtime = _build_memory_plugin_runtime(
            config=config,
            workspace=workspace,
            provider=provider,
            light_provider=light_provider,
            http_resources=http_resources,
            roles=runtime_roles if runtime_roles is not None else RoleStore(workspace),
            event_publisher=event_publisher,
        )
        engine = plugin_runtime.engine
        resources = plugin_runtime.resources
        if not resources:
            closeables.extend(plugin_runtime.closeables)
        track_build_closeables(closeables)
        register_memory_meta_tools(
            tools,
            engine,
        )
    else:
        engine = DisabledMemoryEngine()

    return MemoryRuntime(
        markdown=markdown,
        engine=engine,
        closeables=closeables,
        resources=resources,
    )


def _memory_keep_count(window: int) -> int:
    aligned_window = max(4, ((max(1, window) + 3) // 4) * 4)
    return aligned_window // 2
