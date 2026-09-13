from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from agent.plugin_host import PluginKernel

from agent.config_models import Config, WiringConfig
from agent.core.proactive_turn.gates import ProactiveGate
from agent.core.proactive_turn.strategies import (
    SceneFollowupStrategy,
    RelationshipStrategy,
)
from agent.core.proactive_turn.scene_subscription import SceneFollowupSubscription
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
from agent.screen_observation import (
    ScreenObservationService,
    build_screen_observation_service,
)
from agent.retrieval.default_pipeline import DefaultMemoryRetrievalPipeline
from agent.scheduler import SchedulerService
from agent.tools.message_push import MessagePushTool
from agent.tools.observe_screen import ObserveScreenTool
from agent.tools.registry import ToolRegistry
from core.scene.controller import SceneAwarenessController
from core.scene.demand import SceneObservationDemand
from core.scene.service import SceneObservationService
from core.scene.state import SceneStateStore
from core.common.cleanup import run_cleanup_steps
from bootstrap.paths import REPOSITORY_ROOT, resource_root, plugin_roots
from bootstrap.runtime.construction import track_build_resource
from bootstrap.toolsets.meta import (
    build_readonly_tools,
)
from bootstrap.toolsets.protocol import ToolsetDeps
from bootstrap.toolsets.schedule import (
    build_scheduler,
)
from bootstrap.wiring import (
    wire_turn_lifecycle,
    resolve_context_factory,
    resolve_memory_toolset_provider,
    resolve_toolset_provider,
)
from agent.lifecycle.facade import TurnLifecycle
from bootstrap.providers import build_providers
from bus.event_bus import EventBus
from bus.processing import ProcessingState
from bus.queue import MessageBus
from core.common.channel_identifiers import chat_ids_equal
from core.memory.markdown import MemoryLifecycleBindRequest, MarkdownMemoryMaintenance
from core.memory.runtime import MemoryRuntime
from core.net.http import SharedHttpResources
from core.roles import (
    RelationshipSnapshotOptimizer,
    RoleRelationshipRuntimeService,
    RoleRepository,
    RoleStore,
    RoleRuntimeRegistry,
)
from core.roles.model_runtime import RoleModelRuntime
from core.roles.self_initializer import RoleSelfInitializer
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from infra.screen_capture import PrimaryScreenCapture
from conversation.push_sync import ExternalImageSyncService
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager

logger = logging.getLogger(__name__)


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
    role_runtime_registry: RoleRuntimeRegistry
    scene_service: SceneObservationService | None = None
    image_sync_service: ExternalImageSyncService | None = None
    agent_provider: LLMProvider | None = None
    plugin_manager: "PluginKernel | None" = None
    memory_optimizer: Any | None = None
    screen_observation: ScreenObservationService | None = None
    additional_providers: list[LLMProvider] = field(default_factory=list)
    proactive_motives: list[ProactiveGate] = field(default_factory=list)
    scene_followup_subscription: SceneFollowupSubscription | None = None

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
        """Renders this generation\'s lifecycle module configuration."""
        from bootstrap.runtime.inspection import inspect_core_modules

        return await inspect_core_modules(self)

    def assert_hot_unloadable(self) -> None:
        """Refuses live replacement before scene, event, or provider teardown starts."""
        if self.plugin_manager is not None:
            self.plugin_manager.assert_hot_unloadable()

    async def stop(self, *, force: bool = False) -> None:
        """Drains owned work and releases resources; shutdown/rollback may force cleanup."""
        if not force:
            self.assert_hot_unloadable()
        steps = []
        if self.scene_service is not None:
            steps.append(("scene.close", self.scene_service.close))
        spawn = self.tools.get_tool("spawn")
        if spawn is not None:
            steps.append(("spawn.drain", spawn.manager.drain))
        steps.extend(
            [
                ("event_bus.drain", self.event_bus.drain),
                (
                    "memory.maintenance.drain",
                    self.memory_runtime.markdown.maintenance.drain,
                ),
            ]
        )
        if self.scene_followup_subscription is not None:

            async def stop_scene_followup() -> None:
                self.scene_followup_subscription.stop()

            steps.append(("scene_followup.stop", stop_scene_followup))
        if self.plugin_manager is not None:
            steps.append(
                (
                    "plugins.terminate",
                    lambda: self.plugin_manager.terminate_all(force=force),
                )
            )
        steps.extend(
            [
                ("mcp.shutdown", self.mcp_registry.shutdown),
                ("event_bus.aclose", self.event_bus.aclose),
                ("provider.aclose", self.provider.aclose),
            ]
        )
        resolver = self.role_runtime_registry.model_resolver
        if resolver is not None:
            steps.append(("role_models.aclose", resolver.aclose))
        steps.extend(
            (f"provider:{index}", provider.aclose)
            for index, provider in enumerate(self.additional_providers)
        )
        await run_cleanup_steps(*steps)


def build_registered_tools(
    config: Config,
    workspace: Path,
    http_resources: SharedHttpResources,
    *,
    bus: MessageBus,
    provider,
    light_provider,
    session_store=None,
    tools: ToolRegistry | None = None,
    event_publisher: EventBus | None = None,
    agent_loop_provider: Callable[[], Any] | None = None,
    role_repository: RoleRepository | None = None,
    role_runtime_registry: RoleRuntimeRegistry | None = None,
    shared_push_tool: MessagePushTool | None = None,
    shared_scheduler: SchedulerService | None = None,
) -> tuple[
    ToolRegistry,
    MessagePushTool,
    SchedulerService,
    McpServerRegistry,
    MemoryRuntime,
    ScreenObservationService,
]:
    from session.store import SessionStore

    # ── 第一阶段：建服务（依赖无顺序陷阱）────────────────────────────────────
    wiring = getattr(config, "wiring", WiringConfig())
    tools = tools or ToolRegistry()
    multimodal = getattr(config, "multimodal", True)
    readonly_tools = build_readonly_tools(http_resources, multimodal=multimodal)
    store = session_store or SessionStore(workspace / "sessions.db")
    push_tool = shared_push_tool or MessagePushTool(event_bus=event_publisher)
    memory_result = resolve_memory_toolset_provider(wiring.memory).register(
        tools,
        ToolsetDeps(
            config=config,
            workspace=workspace,
            provider=provider,
            light_provider=light_provider,
            http_resources=http_resources,
            event_publisher=event_publisher,
            role_runtime_registry=role_runtime_registry,
        ),
    )
    memory_runtime = memory_result.extras["memory_runtime"]
    screen_observation = build_screen_observation_service(
        roles=role_repository or RoleRepository(RoleStore(workspace)),
        memory=memory_runtime.engine,
        role_runtime_registry=role_runtime_registry,
    )
    tools.register(
        ObserveScreenTool(
            capture=PrimaryScreenCapture(),
            analyzer=screen_observation,
        ),
        always_on=True,
        risk="read-only",
        search_hint="屏幕 桌面 当前窗口 观察主屏",
    )
    scheduler = shared_scheduler or build_scheduler(
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
                bus=bus,
                memory_engine=memory_runtime.engine,
                scheduler=scheduler,
                event_publisher=event_publisher,
                role_runtime_registry=role_runtime_registry,
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

    track_build_resource(mcp_registry, mcp_registry.shutdown)
    return (
        tools,
        push_tool,
        scheduler,
        mcp_registry,
        memory_runtime,
        screen_observation,
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
    role_runtime_registry: RoleRuntimeRegistry | None = None,
) -> AgentLoopDeps:
    wiring = getattr(config, "wiring", WiringConfig())
    context = resolve_context_factory(wiring.context)(
        workspace,
        memory_runtime.markdown.store,
    )
    if isinstance(context, ContextBuilder):
        context.set_media_capabilities(
            multimodal=config.multimodal,
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
        role_runtime_registry=role_runtime_registry,
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
        role_runtime_registry=role_runtime_registry,
    )


def _bind_memory_lifecycle_if_supported(
    *,
    markdown: MarkdownMemoryMaintenance,
    session_manager: SessionManager,
    relationship_runtime: RoleRelationshipRuntimeService,
    relationship_optimizer: RelationshipSnapshotOptimizer,
) -> None:
    async def _after_consolidation(session: object) -> None:
        await relationship_runtime.refresh_snapshot_after_consolidation(
            session,
            optimizer=relationship_optimizer,
        )

    markdown.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=session_manager.get_or_create,
            commit_consolidation=session_manager.commit_consolidation,
            after_consolidation=_after_consolidation,
        )
    )


def _resolve_plugin_llm_dependencies(
    config: Config,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
) -> tuple[LLMProvider, str]:
    """Use the main LLM when no dedicated lightweight model is configured."""
    return light_provider or provider, config.light_model or config.model


def build_core_runtime(
    config: Config,
    workspace: Path,
    http_resources: SharedHttpResources,
    *,
    shared: CoreRuntime | None = None,
    event_bus: EventBus | None = None,
    agent_loop_provider: Callable[[], Any] | None = None,
    event_outlet: EventBus | None = None,
) -> CoreRuntime:
    """Builds version-owned capabilities around stable transport and state owners."""
    bus = shared.bus if shared is not None else MessageBus()
    event_bus = event_bus or EventBus()
    track_build_resource(event_bus, event_bus.aclose)
    provider, light_provider, agent_provider = build_providers(config)
    loop_provider = provider
    loop_model = config.model
    session_manager = (
        shared.session_manager if shared is not None else SessionManager(workspace)
    )
    if shared is None:
        track_build_resource(session_manager._store, session_manager._store.close)
    default_registration_id = (
        config.model_registrations[0].id if config.model_registrations else ""
    )
    role_store = (
        shared.role_runtime_registry.repository.store
        if shared
        else RoleStore(workspace)
    )
    if shared is None:
        role_store.migrate_model_selections(
            dialogue_registration_id=default_registration_id,
            visual_registration_id="",
        )
    role_model_resolver = RoleModelRuntime(
        role_store=role_store,
        registrations=config.model_registrations,
        dev_mode=config.dev_mode,
    )
    track_build_resource(role_model_resolver, role_model_resolver.aclose)
    role_repository = RoleRepository(role_store)
    role_runtime_registry = RoleRuntimeRegistry(
        role_repository,
        model_resolver=role_model_resolver,
        shared_execution=shared.role_runtime_registry if shared else None,
        self_initializer=RoleSelfInitializer(role_store, LlmRoleSelfSeedGenerator()),
    )
    loop_ref: dict[str, AgentLoop] = {}
    tools, push_tool, scheduler, mcp_registry, memory_runtime, screen_observation = (
        build_registered_tools(
            config,
            workspace,
            http_resources,
            bus=bus,
            provider=provider,
            light_provider=light_provider,
            session_store=session_manager._store,
            event_publisher=event_bus,
            role_runtime_registry=role_runtime_registry,
            agent_loop_provider=agent_loop_provider or (lambda: loop_ref.get("loop")),
            role_repository=role_repository,
            shared_push_tool=(
                shared.push_tool
                if shared
                else MessagePushTool(event_bus=event_outlet or event_bus)
            ),
            shared_scheduler=shared.scheduler if shared else None,
        )
    )
    presence = (
        shared.presence if shared is not None else PresenceStore(session_manager._store)
    )
    if shared is not None:
        memory_runtime.markdown.maintenance.share_execution(
            shared.memory_runtime.markdown.maintenance
        )
    relationship_runtime = (
        shared.relationship_runtime
        if shared is not None
        else RoleRelationshipRuntimeService(
            workspace,
            role_store=role_store,
            session_manager=session_manager,
            presence=presence,
        )
    )
    processing_state = (
        shared.loop.processing_state if shared is not None else ProcessingState()
    )
    if processing_state is None:
        raise RuntimeError("Shared runtime is missing its processing state")
    image_sync_service = (
        shared.image_sync_service
        if shared is not None
        else ExternalImageSyncService(
            session_manager=session_manager,
            event_bus=event_outlet or event_bus,
        )
    )
    if shared is None:
        push_tool.set_role_target_validator(
            lambda role_id, channel, chat_id: _validate_role_target(
                role_repository,
                role_id=role_id,
                channel=channel,
                chat_id=chat_id,
            )
        )
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
        role_runtime_registry=role_runtime_registry,
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
                multimodal=config.multimodal,
            ),
            memory=MemoryConfig(
                window=config.memory_window,
                input_token_threshold=config.memory_consolidation_input_token_threshold,
            ),
        ),
    )
    loop_ref["loop"] = loop
    if shared is not None:
        loop.share_execution(shared.loop)
    wire_turn_lifecycle(
        lifecycle=TurnLifecycle(event_bus),
        active_turn_states=loop.active_turn_states,
    )

    from agent.plugin_host import HostServices, PluginKernel

    plugin_light_provider, plugin_light_model = _resolve_plugin_llm_dependencies(
        config,
        provider,
        light_provider,
    )
    scene_demand = SceneObservationDemand()
    scene_service = SceneObservationService(
        SceneAwarenessController(
            role_store=RoleStore(workspace),
            session_manager=session_manager,
            event_bus=event_bus,
            kv_store=(
                shared.scene_service.controller.state
                if shared is not None and shared.scene_service is not None
                else SceneStateStore(
                    workspace,
                    (
                        resource_root() / "plugins",
                        REPOSITORY_ROOT / "apps" / "backend" / "plugins",
                    ),
                )
            ),
            light_provider=plugin_light_provider,
            light_model=plugin_light_model,
            needs_observation=lambda role: config.scene_observation_enabled
            and (
                (role.proactive.enabled and config.proactive_strategies.scene_followup)
                or scene_demand.needed(role)
            ),
        ),
        event_bus,
    )
    plugin_manager = PluginKernel(
        plugin_dirs=_resolve_plugin_dirs(workspace),
        services=HostServices(
            event_bus=event_bus,
            tool_registry=tools,
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
            memory_engine=memory_runtime.engine,
            app_config=config,
            light_provider=plugin_light_provider,
            light_model=plugin_light_model,
            plugin_configs=config.plugins,
            relationship_runtime=relationship_runtime,
            legacy_plugin_root=_legacy_plugin_root(),
            role_runtime_registry=role_runtime_registry,
            scene_observations=scene_demand,
            is_reload=shared is not None,
            previously_active_plugins=(
                frozenset(
                    row["id"]
                    for row in shared.plugin_manager.states()
                    if row["state"] == "ACTIVE"
                )
                if shared is not None and shared.plugin_manager is not None
                else frozenset()
            ),
        ),
        namespace=uuid4().hex,
        strict=shared is not None,
    )

    return CoreRuntime(
        config=config,
        http_resources=http_resources,
        loop=loop,
        bus=bus,
        event_bus=event_bus,
        tools=tools,
        push_tool=push_tool,
        image_sync_service=image_sync_service,
        session_manager=session_manager,
        scheduler=scheduler,
        provider=provider,
        light_provider=light_provider,
        agent_provider=agent_provider,
        mcp_registry=mcp_registry,
        memory_runtime=memory_runtime,
        presence=presence,
        relationship_runtime=relationship_runtime,
        role_runtime_registry=role_runtime_registry,
        plugin_manager=plugin_manager,
        scene_service=scene_service,
        screen_observation=screen_observation,
        proactive_motives=[
            *(
                [SceneFollowupStrategy(relationship_runtime)]
                if config.proactive_strategies.scene_followup
                else []
            ),
            *(
                [RelationshipStrategy(relationship_runtime)]
                if config.proactive_strategies.relationship
                else []
            ),
        ],
        scene_followup_subscription=(
            SceneFollowupSubscription(event_bus, relationship_runtime)
            if config.proactive_strategies.scene_followup
            else None
        ),
    )


def _resolve_plugin_dirs(workspace: Path) -> list[Path]:
    """Resolves the top-level `plugins/` directory for dev and frozen runs."""
    return plugin_roots()


def _legacy_plugin_root() -> Path | None:
    """插件包上移到仓库顶层之前的位置，用于一次性迁移遗留的本地状态。

    `.kv.json` 被 gitignore 覆盖，目录重命名经 git
    落到本地时不会跟着搬，会静默留在旧路径（见 #178 / #209）。打包形态下
    这个目录不存在，返回 None。
    """
    legacy = REPOSITORY_ROOT / "apps" / "backend" / "plugins"
    return legacy if legacy.is_dir() else None


def _role_owns_channel_target(
    repository: RoleRepository,
    *,
    role_id: str,
    channel: str,
    chat_id: str,
) -> bool:
    clean_channel = str(channel).strip()
    clean_chat_id = str(chat_id).strip()
    role = repository.get_required(role_id)
    return any(
        binding.channel == clean_channel
        and chat_ids_equal(clean_channel, binding.chat_id, clean_chat_id)
        for binding in role.channel_bindings
    )


def _validate_role_target(
    repository: RoleRepository,
    *,
    role_id: str,
    channel: str,
    chat_id: str,
) -> bool | str:
    """Validates a role-scoped push and explains channel mismatches."""

    if _role_owns_channel_target(
        repository,
        role_id=role_id,
        channel=channel,
        chat_id=chat_id,
    ):
        return True

    role = repository.get_required(role_id)
    matching_binding = next(
        (
            binding
            for binding in role.channel_bindings
            if chat_ids_equal(binding.channel, binding.chat_id, chat_id)
        ),
        None,
    )
    if matching_binding is not None:
        return (
            f"角色 {role_id} 未绑定目标渠道: {channel}:{chat_id}；"
            f"该会话已绑定渠道 {matching_binding.channel}，请使用 channel={matching_binding.channel}"
        )
    return False
