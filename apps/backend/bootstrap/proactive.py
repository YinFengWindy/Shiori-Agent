from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from agent.config_models import Config
from agent.looping.core import AgentLoop
from agent.provider import LLMProvider
from agent.tool_hooks import ToolHook
from agent.core.proactive_turn.gates import ProactiveGate
from agent.tools.message_push import MessagePushTool
from conversation.service import desktop_thread_id
from core.common.channel_directory import DESKTOP_CHANNEL
from core.desktop_presence import DesktopPresence
from core.roles import RoleRecord, RoleStore
from core.roles.model_runtime import RoleAwareProvider
from core.roles.role_prompt_compiler import RoleKnowledgeMatcher, RolePromptCompiler
from proactive_v2.config_loader import load_proactive_config
from proactive_v2.loop import ProactiveLoop
from proactive_v2.memory_optimizer import MemoryOptimizer, MemoryOptimizerLoop
from proactive_v2.presence import PresenceStore
from proactive_v2.state import ProactiveStateStore
from session.manager import SessionManager

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from core.memory.markdown import MarkdownMemoryStore
    from core.memory.runtime import MemoryRuntime
    from core.roles.role_runtime import RoleRuntimeRegistry

logger = logging.getLogger(__name__)


def _build_proactive_provider(config: Config, provider: LLMProvider) -> LLMProvider:
    api_key = str(getattr(config, "api_key", "") or "").strip()
    base_url = getattr(config, "base_url", None)
    if not api_key:
        return provider

    extra_body = dict(getattr(config, "extra_body", {}) or {})
    extra_body.pop("enable_thinking", None)
    return LLMProvider(
        api_key=api_key,
        base_url=base_url,
        extra_body=extra_body,
        provider_name=str(getattr(config, "provider", "") or ""),
        force_disable_thinking=True,
    )


def build_proactive_runtime(
    config: Config,
    workspace: Path,
    *,
    session_manager: SessionManager,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    push_tool: MessagePushTool,
    memory_store: "MemoryRuntime | None",
    presence: PresenceStore,
    agent_loop: AgentLoop,
    tool_hooks: list[ToolHook] | None = None,
    proactive_gates: list[ProactiveGate] | None = None,
    proactive_motives: list[ProactiveGate] | None = None,
    event_bus: "EventBus | None" = None,
    provider_consumer: Callable[[LLMProvider], None] | None = None,
    desktop_presence: DesktopPresence,
) -> tuple[list, dict[str, ProactiveLoop]]:
    """Builds one proactive loop per enabled role.

    ``desktop_presence`` is the app-level report the loops read when choosing
    where each proactive message goes.
    """
    tasks: list = []
    roles = [
        role for role in RoleStore(workspace).list_roles() if role.proactive.enabled
    ]
    if not roles:
        return tasks, {}

    # 2. 为每个角色创建独立配置、状态与 agent loop。
    proactive_provider = _build_proactive_provider(config, provider)
    if provider_consumer is not None and proactive_provider is not provider:
        provider_consumer(proactive_provider)
    loops: dict[str, ProactiveLoop] = {}
    role_runtime_registry = agent_loop.role_runtime_registry
    role_aware_provider = RoleAwareProvider(proactive_provider)
    for role in roles:
        proactive_cfg = _build_role_proactive_config(role)
        proactive_state = ProactiveStateStore(
            workspace / "roles" / role.id / "proactive.db"
        )
        loop = ProactiveLoop(
            session_manager=session_manager,
            provider=role_aware_provider,
            push_tool=push_tool,
            config=proactive_cfg,
            model=config.model,
            max_tokens=config.max_tokens,
            state_store=proactive_state,
            memory_store=memory_store,
            presence=presence,
            light_provider=role_aware_provider,
            light_model=config.model,
            passive_busy_fn=(
                agent_loop.processing_state.is_busy
                if agent_loop.processing_state
                else None
            ),
            shared_tools=getattr(agent_loop, "tools", None),
            tool_hooks=tool_hooks,
            proactive_gates=proactive_gates,
            proactive_motives=proactive_motives,
            event_bus=event_bus,
            role_prompt_fn=_build_role_prompt_resolver(workspace, role.id),
            tick_dispatcher=_build_role_tick_dispatcher(
                role_id=role.id,
                registry=role_runtime_registry,
            ),
            desktop_presence=desktop_presence,
        )
        loops[role.id] = loop
        tasks.append(loop.run())
    return tasks, loops


def _build_role_prompt_resolver(workspace: Path, role_id: str):
    def resolve() -> str:
        role = RoleStore(workspace).get_role(role_id)
        if role is None:
            raise ValueError(f"role not found for proactive generation: {role_id}")
        prompt = (
            RolePromptCompiler()
            .compile(
                role,
                matched_knowledge_entries=RoleKnowledgeMatcher().match(
                    role.profile.knowledge_base
                ),
            )
            .content.strip()
        )
        if not prompt:
            raise ValueError(f"role.system_prompt required: {role_id}")
        return prompt

    return resolve


def _build_role_proactive_config(role: RoleRecord):
    """Builds the runtime proactive config from one authoritative role snapshot."""
    proactive = role.proactive
    agent = dict(getattr(proactive, "agent", {}) or {})
    agent.pop("model", None)
    return load_proactive_config(
        {
            "enabled": proactive.enabled,
            "profile": str(getattr(proactive, "profile", "daily") or "daily"),
            # Delivery targets come from the role's candidate sessions, chosen
            # per message; the config only names the role.
            "target": {"role_id": role.id},
            "overrides": dict(getattr(proactive, "overrides", {}) or {}),
            "agent": agent,
            "drift": dict(getattr(proactive, "drift", {}) or {}),
        }
    )


def _build_role_tick_dispatcher(
    *,
    role_id: str,
    registry,
):
    if registry is None:
        raise RuntimeError("主动任务需要 RoleRuntimeRegistry")

    async def dispatch(operation):
        # A tick starts before its delivery target is chosen, so it runs under
        # the role's own session (the desktop thread of ``role:<id>``).
        context = registry.create_context(
            role_id=role_id,
            thread_id=desktop_thread_id(role_id),
            transport_channel=DESKTOP_CHANNEL,
            transport_chat_id=f"role:{role_id}",
            source="proactive",
            work_kind="proactive_tick",
        )

        async def run_with_model_snapshot():
            runtime = await registry.get(role_id)
            with runtime.activate_model("chat"):
                return await operation()

        return await registry.dispatch_proactive_tick(
            context,
            run_with_model_snapshot,
        )

    return dispatch


def build_memory_optimizer_task(
    config: Config,
    *,
    provider: LLMProvider,
    memory_store: "MarkdownMemoryStore",
    role_runtime_registry: "RoleRuntimeRegistry | None" = None,
    loop_consumer: Callable[[MemoryOptimizerLoop], None] | None = None,
) -> tuple[list, "MemoryOptimizer | None"]:
    if not config.memory_optimizer_enabled or not config.model_registrations:
        logger.info("MemoryOptimizerLoop 已禁用（memory_optimizer_enabled=false）")
        return [], None

    mem_optimizer = MemoryOptimizer(
        memory=memory_store,
        provider=provider,
        model=config.model,
        workspace=memory_store.memory_dir.parent,
        role_runtime_registry=role_runtime_registry,
    )
    interval = config.memory_optimizer_interval_seconds
    logger.info(
        "MemoryOptimizerLoop 已启动，间隔=%ss (%.1fh)", interval, interval / 3600
    )
    loop = MemoryOptimizerLoop(mem_optimizer, interval_seconds=interval)
    if loop_consumer is not None:
        loop_consumer(loop)
    return [loop.run()], mem_optimizer
