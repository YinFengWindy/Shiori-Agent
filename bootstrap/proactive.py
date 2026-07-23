from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent.config_models import Config
from agent.looping.core import AgentLoop
from agent.provider import LLMProvider
from agent.tool_hooks import ToolHook
from agent.core.proactive_turn.gates import ProactiveGate
from agent.tools.message_push import MessagePushTool
from core.roles import RoleRecord, RoleStore
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

logger = logging.getLogger(__name__)


def _build_proactive_provider(config: Config, provider: LLMProvider) -> LLMProvider:
    api_key = str(getattr(config, "api_key", "") or "").strip()
    system_prompt = str(getattr(config, "system_prompt", "") or "")
    base_url = getattr(config, "base_url", None)
    if not api_key:
        return provider

    extra_body = dict(getattr(config, "extra_body", {}) or {})
    extra_body.pop("enable_thinking", None)
    return LLMProvider(
        api_key=api_key,
        base_url=base_url,
        system_prompt=system_prompt,
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
    event_bus: "EventBus | None" = None,
) -> tuple[list, dict[str, ProactiveLoop]]:
    tasks: list = []
    roles = [role for role in RoleStore(workspace).list_roles() if role.proactive.enabled]
    if not roles:
        return tasks, {}

    # 2. 为每个角色创建独立配置、状态与 agent loop。
    proactive_provider = _build_proactive_provider(config, provider)
    loops: dict[str, ProactiveLoop] = {}
    role_world_registry = agent_loop.role_world_registry
    for role in roles:
        target = role.proactive
        proactive_cfg = _build_role_proactive_config(role)
        proactive_state = ProactiveStateStore(
            workspace / "roles" / role.id / "proactive.db"
        )
        loop = ProactiveLoop(
            session_manager=session_manager,
            provider=proactive_provider,
            push_tool=push_tool,
            config=proactive_cfg,
            model=config.model,
            max_tokens=config.max_tokens,
            state_store=proactive_state,
            memory_store=memory_store,
            presence=presence,
            light_provider=light_provider,
            light_model=config.light_model,
            passive_busy_fn=(
                agent_loop.processing_state.is_busy if agent_loop.processing_state else None
            ),
            shared_tools=getattr(agent_loop, "tools", None),
            tool_hooks=tool_hooks,
            proactive_gates=proactive_gates,
            event_bus=event_bus,
            tick_dispatcher=_build_role_tick_dispatcher(
                role_id=role.id,
                channel=target.target_channel,
                chat_id=target.target_chat_id,
                registry=role_world_registry,
            ),
        )
        loops[role.id] = loop
        tasks.append(loop.run())
    return tasks, loops


def _build_role_proactive_config(role: RoleRecord):
    """Builds the runtime proactive config from one authoritative role snapshot."""
    target = role.proactive
    return load_proactive_config(
        {
            "enabled": target.enabled,
            "profile": str(getattr(target, "profile", "daily") or "daily"),
            "target": {
                "role_id": role.id,
                "channel": target.target_channel,
                "chat_id": target.target_chat_id,
            },
            "overrides": dict(getattr(target, "overrides", {}) or {}),
            "agent": dict(getattr(target, "agent", {}) or {}),
            "drift": dict(getattr(target, "drift", {}) or {}),
        }
    )


def _build_role_tick_dispatcher(*, role_id: str, channel: str, chat_id: str, registry):
    if registry is None:
        raise RuntimeError("主动任务需要 RoleWorldRegistry")

    async def dispatch(operation):
        context = registry.create_context(
            role_id=role_id,
            thread_id=f"thread:{role_id}:{channel}:{chat_id}",
            transport_channel=channel,
            transport_chat_id=chat_id,
            source="proactive",
            work_kind="proactive_tick",
        )
        return await registry.dispatch_proactive_tick(context, operation)

    return dispatch


def build_memory_optimizer_task(
    config: Config,
    *,
    provider: LLMProvider,
    memory_store: "MarkdownMemoryStore",
) -> tuple[list, "MemoryOptimizer | None"]:
    if not config.memory_optimizer_enabled:
        logger.info("MemoryOptimizerLoop 已禁用（memory_optimizer_enabled=false）")
        return [], None

    mem_optimizer = MemoryOptimizer(
        memory=memory_store,
        provider=provider,
        model=config.model,
        workspace=memory_store.memory_dir.parent,
    )
    interval = config.memory_optimizer_interval_seconds
    logger.info("MemoryOptimizerLoop 已启动，间隔=%ss (%.1fh)", interval, interval / 3600)
    return [MemoryOptimizerLoop(mem_optimizer, interval_seconds=interval).run()], mem_optimizer
