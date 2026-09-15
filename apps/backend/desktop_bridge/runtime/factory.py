"""Assembly of the desktop handlers for one runtime generation."""

from __future__ import annotations

from bootstrap.tools import CoreRuntime
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService


def build_desktop_service(
    runtime: CoreRuntime, role_store: RoleStore, *, activate_transport: bool = True
) -> DesktopBridgeService:
    """Captures generation-owned dependencies without starting background work."""
    spawn = runtime.tools.get_tool("spawn")
    registry = runtime.role_runtime_registry
    plugin_manager = runtime.plugin_manager
    return DesktopBridgeService(
        workspace=runtime.session_manager.workspace,
        role_store=role_store,
        session_manager=runtime.session_manager,
        agent_loop=runtime.loop,
        event_bus=runtime.event_bus,
        config=runtime.config,
        model_resolver=registry.model_resolver if registry is not None else None,
        activate_transport=activate_transport,
        push_tool=runtime.push_tool,
        relationship_runtime=runtime.relationship_runtime,
        presence=runtime.presence,
        scheduler=runtime.scheduler,
        subagent_manager=getattr(spawn, "manager", None),
        memory_optimizer=runtime.memory_optimizer,
        role_runtime_registry=registry,
        memory_engine=runtime.memory_runtime.engine,
        plugin_rpc_registry=plugin_manager.rpc if plugin_manager is not None else None,
    )
