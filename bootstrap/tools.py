from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from agent.plugins.manager import PluginManager

logger = logging.getLogger(__name__)

from agent.config_models import Config, WiringConfig
from agent.context import ContextBuilder
from agent.looping.core import AgentLoop
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    LLMServices,
    MemoryConfig,
    MemoryServices,
    SessionServices,
)
from agent.mcp.registry import McpServerRegistry
from agent.provider import LLMProvider
from agent.retrieval.default_pipeline import DefaultMemoryRetrievalPipeline
from agent.scheduler import SchedulerService
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.outbound import BusOutboundPort
from bootstrap.toolsets.mcp import McpToolsetProvider
from bootstrap.toolsets.memory import MemoryToolsetProvider
from bootstrap.toolsets.meta import (
    CommonMetaToolsetProvider,
    SpawnToolsetProvider,
    build_readonly_tools,
)
from bootstrap.toolsets.protocol import ToolsetDeps
from bootstrap.toolsets.schedule import (
    SchedulerToolsetProvider,
    build_scheduler,
)
from bootstrap.wiring import (
    wire_turn_lifecycle,
    resolve_context_factory,
    resolve_memory_toolset_provider,
    resolve_toolset_provider,
)
from agent.lifecycle.facade import TurnLifecycle
from bootstrap.providers import build_providers, build_vl_provider
from bootstrap.conversation import migrate_workspace_conversations
from bus.event_bus import EventBus
from bus.processing import ProcessingState
from bus.queue import MessageBus
from core.memory.markdown import MemoryLifecycleBindRequest, MarkdownMemoryMaintenance
from core.memory.runtime import MemoryRuntime
from core.net.http import SharedHttpResources
from core.roles import (
    RelationshipSnapshotOptimizer,
    RoleConfigMigrator,
    RoleRelationshipRuntimeService,
    RoleRepository,
    RoleStore,
)
from proactive_v2.presence import PresenceStore
from session.manager import Session, SessionManager


@dataclass
class CoreRuntime:
    config: Config
    http_resources: SharedHttpResources
    loop: AgentLoop
    bus: MessageBus
    event_bus: EventBus
    tools: ToolRegistry
    push_tool: MessagePushTool
    session_manager: SessionManager
    scheduler: SchedulerService
    provider: LLMProvider
    light_provider: LLMProvider | None
    mcp_registry: McpServerRegistry
    memory_runtime: MemoryRuntime
    presence: PresenceStore
    relationship_runtime: RoleRelationshipRuntimeService
    agent_provider: LLMProvider | None = None
    plugin_manager: "PluginManager | None" = None

    async def start(self) -> None:
        self.mcp_registry.start_connect_all_background()
        if self.plugin_manager is not None:
            await self.plugin_manager.load_all()
            logger.info("插件加载完成: %d 个", self.plugin_manager.loaded_count)
            self.loop.add_before_turn_plugin_modules(
                self.plugin_manager.before_turn_modules,
            )
            self.loop.add_before_reasoning_plugin_modules(
                self.plugin_manager.before_reasoning_modules,
            )
            self.loop.add_prompt_render_plugin_modules(
                self.plugin_manager.prompt_render_modules,
            )
            self.loop.add_before_step_plugin_modules(
                self.plugin_manager.before_step_modules,
            )
            self.loop.add_after_step_plugin_modules(
                self.plugin_manager.after_step_modules,
            )
            self.loop.add_after_reasoning_plugin_modules(
                self.plugin_manager.after_reasoning_modules,
            )
            self.loop.add_after_turn_plugin_modules(
                self.plugin_manager.after_turn_modules,
            )
            if self.plugin_manager.tool_hooks:
                self.loop.add_tool_hooks(self.plugin_manager.tool_hooks)
                spawn_tool = self.tools.get_tool("spawn")
                if spawn_tool is not None and hasattr(spawn_tool, "add_tool_hooks"):
                    spawn_tool.add_tool_hooks(self.plugin_manager.tool_hooks)

    async def inspect_modules(self) -> str:
        if self.plugin_manager is not None:
            await self.plugin_manager.load_all()

        from agent.lifecycle.phase import inspect_phase
        from agent.lifecycle.phases.after_reasoning import (
            default_after_reasoning_modules,
        )
        from agent.lifecycle.phases.after_step import default_after_step_modules
        from agent.lifecycle.phases.after_turn import default_after_turn_modules
        from agent.lifecycle.phases.before_reasoning import (
            default_before_reasoning_modules,
        )
        from agent.lifecycle.phases.before_step import default_before_step_modules
        from agent.lifecycle.phases.before_turn import default_before_turn_modules
        from agent.lifecycle.phases.prompt_render import default_prompt_render_modules

        manager = self.plugin_manager
        before_turn_modules = manager.before_turn_modules if manager is not None else []
        before_reasoning_modules = (
            manager.before_reasoning_modules if manager is not None else []
        )
        prompt_render_modules = manager.prompt_render_modules if manager is not None else []
        before_step_modules = manager.before_step_modules if manager is not None else []
        after_step_modules = manager.after_step_modules if manager is not None else []
        after_reasoning_modules = (
            manager.after_reasoning_modules if manager is not None else []
        )
        after_turn_modules = manager.after_turn_modules if manager is not None else []

        agent_core = cast(Any, getattr(self.loop, "_agent_core"))
        pipeline = agent_core.pipeline
        reasoner = getattr(self.loop, "_reasoner", None)
        context = getattr(reasoner, "_context", None)

        phases = [
            (
                "before_turn",
                default_before_turn_modules(
                    self.event_bus,
                    self.session_manager,
                    cast(Any, getattr(pipeline, "_context_store", None)),
                    plugin_modules=cast(Any, before_turn_modules),
                ),
            ),
            (
                "before_reasoning",
                default_before_reasoning_modules(
                    self.event_bus,
                    self.tools,
                    self.session_manager,
                    cast(Any, context),
                    plugin_modules=cast(Any, before_reasoning_modules),
                ),
            ),
            (
                "prompt_render",
                default_prompt_render_modules(
                    self.event_bus,
                    cast(Any, context),
                    plugin_modules=cast(Any, prompt_render_modules),
                ),
            ),
            (
                "before_step",
                default_before_step_modules(
                    self.event_bus,
                    plugin_modules=cast(Any, before_step_modules),
                ),
            ),
            (
                "after_step",
                default_after_step_modules(
                    self.event_bus,
                    plugin_modules=cast(Any, after_step_modules),
                ),
            ),
            (
                "after_reasoning",
                default_after_reasoning_modules(
                    self.event_bus,
                    cast(Any, getattr(pipeline, "_session", None)),
                    plugin_modules=cast(Any, after_reasoning_modules),
                ),
            ),
            (
                "after_turn",
                default_after_turn_modules(
                    self.event_bus,
                    cast(Any, getattr(pipeline, "_outbound_port", BusOutboundPort(self.bus))),
                    cast(Any, context),
                    cast(int, getattr(pipeline, "_history_window", 500)),
                    plugin_modules=cast(Any, after_turn_modules),
                ),
            ),
        ]

        parts: list[str] = []
        for phase_name, modules in phases:
            parts.append("=" * 60)
            parts.append(phase_name)
            parts.append("=" * 60)
            parts.append(inspect_phase(modules))
        return "\n".join(parts)

    async def stop(self) -> None:
        if self.plugin_manager is not None:
            await self.plugin_manager.terminate_all()
        await self.mcp_registry.shutdown()
        await self.event_bus.aclose()


def build_registered_tools(
    config: Config,
    workspace: Path,
    http_resources: SharedHttpResources,
    *,
    bus: MessageBus,
    provider,
    light_provider,
    vl_provider=None,
    session_store=None,
    tools: ToolRegistry | None = None,
    event_publisher=None,
    agent_loop_provider: Callable[[], Any] | None = None,
) -> tuple[
    ToolRegistry,
    MessagePushTool,
    SchedulerService,
    McpServerRegistry,
    MemoryRuntime,
]:
    from session.store import SessionStore

    # ── 第一阶段：建服务（依赖无顺序陷阱）────────────────────────────────────
    wiring = getattr(config, "wiring", WiringConfig())
    tools = tools or ToolRegistry()
    multimodal = getattr(config, "multimodal", True)
    vl_available = (not multimodal) and bool(getattr(config, "vl_model", ""))
    readonly_tools = build_readonly_tools(
        http_resources, multimodal=multimodal, vl_available=vl_available
    )
    store = session_store or SessionStore(workspace / "sessions.db")
    push_tool = MessagePushTool()
    memory_result = resolve_memory_toolset_provider(wiring.memory).register(
        tools,
        ToolsetDeps(
            config=config,
            workspace=workspace,
            provider=provider,
            light_provider=light_provider,
            http_resources=http_resources,
            event_publisher=event_publisher,
        ),
    )
    memory_runtime = memory_result.extras["memory_runtime"]
    scheduler = build_scheduler(
        workspace,
        push_tool,
        agent_loop_provider=agent_loop_provider,
    )

    # ── 第二阶段：注册工具（所有服务已就绪）──────────────────────────────────
    mcp_registry = None
    for name in wiring.toolsets:
        provider_obj = resolve_toolset_provider(
            name,
            readonly_tools=readonly_tools if name == "meta_common" else None,
        )
        result = provider_obj.register(
            tools,
            ToolsetDeps(
                config=config,
                workspace=workspace,
                session_store=store,
                push_tool=push_tool,
                http_resources=http_resources,
                provider=provider,
                light_provider=light_provider,
                vl_provider=vl_provider,
                vl_model=getattr(config, "vl_model", ""),
                bus=bus,
                memory_engine=memory_runtime.engine,
                scheduler=scheduler,
                event_publisher=event_publisher,
            ),
        )
        maybe_mcp = result.extras.get("mcp_registry")
        if maybe_mcp is not None:
            mcp_registry = maybe_mcp
    if mcp_registry is None:
        from agent.mcp.registry import McpServerRegistry

        mcp_registry = McpServerRegistry(
            config_path=workspace / "mcp_servers.json",
            tool_registry=tools,
        )

    return (
        tools,
        push_tool,
        scheduler,
        mcp_registry,
        memory_runtime,
    )


def _build_loop_deps(
    *,
    config: Config,
    workspace: Path,
    bus: MessageBus,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    tools: ToolRegistry,
    session_manager: SessionManager,
    presence: PresenceStore,
    processing_state: ProcessingState,
    event_bus: EventBus,
    memory_runtime: MemoryRuntime,
    relationship_runtime: RoleRelationshipRuntimeService,
) -> AgentLoopDeps:
    wiring = getattr(config, "wiring", WiringConfig())
    context = resolve_context_factory(wiring.context)(
        workspace,
        memory_runtime.markdown.store,
    )
    if isinstance(context, ContextBuilder):
        context.set_media_capabilities(
            multimodal=bool(getattr(config, "multimodal", True)),
            vl_available=bool(getattr(config, "vl_model", "")),
        )
    memory_engine = memory_runtime.engine
    light = light_provider or provider
    llm_services = LLMServices(provider=provider, light_provider=light)
    memory_services = MemoryServices(engine=memory_engine)
    session_services = SessionServices(
        session_manager=session_manager,
        presence=presence,
        relationship_runtime=relationship_runtime,
    )
    relationship_optimizer = RelationshipSnapshotOptimizer(
        relationship_runtime,
        provider=provider,
        model=config.agent_model or config.model,
    )
    _bind_memory_lifecycle_if_supported(
        markdown=memory_runtime.markdown.maintenance,
        session_manager=session_manager,
        relationship_runtime=relationship_runtime,
        relationship_optimizer=relationship_optimizer,
    )
    retrieval_pipeline = DefaultMemoryRetrievalPipeline(
        memory=memory_services,
    )

    return AgentLoopDeps(
        bus=bus,
        event_bus=event_bus,
        provider=provider,
        tools=tools,
        session_manager=session_manager,
        workspace=workspace,
        presence=presence,
        light_provider=light_provider,
        processing_state=processing_state,
        memory_runtime=memory_runtime,
        retrieval_pipeline=retrieval_pipeline,
        context=context,
        llm_services=llm_services,
        memory_services=memory_services,
        session_services=session_services,
    )


def _bind_memory_lifecycle_if_supported(
    *,
    markdown: MarkdownMemoryMaintenance,
    session_manager: SessionManager,
    relationship_runtime: RoleRelationshipRuntimeService,
    relationship_optimizer: RelationshipSnapshotOptimizer,
) -> None:
    async def _save_session(session: object) -> None:
        await session_manager.save_async(cast(Session, session))

    async def _after_consolidation(session: object) -> None:
        await relationship_runtime.refresh_snapshot_after_consolidation(
            session,
            optimizer=relationship_optimizer,
        )

    markdown.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=session_manager.get_or_create,
            save_session=_save_session,
            after_consolidation=_after_consolidation,
        )
    )


def build_core_runtime(
    config: Config,
    workspace: Path,
    http_resources: SharedHttpResources,
) -> CoreRuntime:
    bus = MessageBus()
    event_bus = EventBus()
    provider, light_provider, agent_provider = build_providers(config)
    vl_provider = build_vl_provider(config)
    # agent_provider is used for the AgentLoop (QA / tool calling).
    # provider (llm.main) is used for consolidation event extraction.
    loop_provider = agent_provider or provider
    loop_model = config.agent_model or config.model
    session_manager = SessionManager(workspace)
    role_store = RoleStore(workspace)
    role_migration = RoleConfigMigrator(
        workspace,
        RoleRepository(role_store),
    ).migrate(config.proactive)
    if (
        role_migration.bindings_migrated
        or role_migration.proactive_migrated
        or role_migration.unresolved_bindings
    ):
        logger.info(
            "角色配置迁移完成: bindings=%d proactive=%d unresolved=%d",
            role_migration.bindings_migrated,
            role_migration.proactive_migrated,
            role_migration.unresolved_bindings,
        )
    migration_summary = migrate_workspace_conversations(workspace, session_manager)
    logger.info(
        "conversation migration complete: migrated=%d unresolved=%d",
        len(migration_summary.migrated_session_keys),
        len(migration_summary.unresolved_session_keys),
    )
    loop_ref: dict[str, AgentLoop] = {}
    tools, push_tool, scheduler, mcp_registry, memory_runtime = (
        build_registered_tools(
            config,
            workspace,
            http_resources,
            bus=bus,
            provider=provider,
            light_provider=light_provider,
            vl_provider=vl_provider,
            session_store=session_manager._store,
            event_publisher=event_bus,
            agent_loop_provider=lambda: loop_ref.get("loop"),
        )
    )
    presence = PresenceStore(session_manager._store)
    relationship_runtime = RoleRelationshipRuntimeService(
        workspace,
        role_store=role_store,
        session_manager=session_manager,
        presence=presence,
    )
    processing_state = ProcessingState()
    loop_deps = _build_loop_deps(
        config=config,
        workspace=workspace,
        bus=bus,
        provider=loop_provider,
        light_provider=light_provider,
        tools=tools,
        session_manager=session_manager,
        presence=presence,
        processing_state=processing_state,
        event_bus=event_bus,
        memory_runtime=memory_runtime,
        relationship_runtime=relationship_runtime,
    )
    loop = AgentLoop(
        loop_deps,
        AgentLoopConfig(
            llm=LLMConfig(
                model=loop_model,
                light_model=config.light_model,
                max_iterations=config.max_iterations,
                max_tokens=config.max_tokens,
                tool_search_enabled=config.tool_search_enabled,
                multimodal=bool(getattr(config, "multimodal", True)),
                vl_available=bool(getattr(config, "vl_model", "")),
            ),
            memory=MemoryConfig(
                window=config.memory_window,
            ),
        ),
    )
    loop_ref["loop"] = loop
    wire_turn_lifecycle(
        lifecycle=TurnLifecycle(event_bus),
        active_turn_states=loop.active_turn_states,
    )

    from agent.plugins.manager import PluginManager as _PluginManager
    plugin_manager = _PluginManager(
        plugin_dirs=_resolve_plugin_dirs(workspace),
        event_bus=event_bus,
        tool_registry=tools,
        workspace=workspace,
        session_manager=session_manager,
        memory_engine=memory_runtime.engine,
        app_config=config,
        plugin_configs=config.plugins,
    )

    return CoreRuntime(
        config=config,
        http_resources=http_resources,
        loop=loop,
        bus=bus,
        event_bus=event_bus,
        tools=tools,
        push_tool=push_tool,
        session_manager=session_manager,
        scheduler=scheduler,
        provider=provider,
        light_provider=light_provider,
        agent_provider=agent_provider,
        mcp_registry=mcp_registry,
        memory_runtime=memory_runtime,
        presence=presence,
        relationship_runtime=relationship_runtime,
        plugin_manager=plugin_manager,
    )


def _resolve_plugin_dirs(workspace: Path) -> list[Path]:
    project_root = Path(__file__).resolve().parent.parent
    return [project_root / "plugins"]
