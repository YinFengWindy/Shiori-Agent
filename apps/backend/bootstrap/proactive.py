from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from agent.config_models import Config
from agent.looping.core import AgentLoop
from agent.provider import LLMProvider, thinking_disabled_provider
from agent.tools.execution import KernelSource
from agent.core.proactive_turn.gates import ProactiveGate
from agent.core.proactive_turn.scene_subscription import SceneFollowupSubscription
from agent.core.proactive_turn.strategies import (
    RelationshipStrategy,
    SceneFollowupStrategy,
)
from agent.tools.message_push import MessagePushTool
from core.memory.group_environment import GroupEnvironment
from core.roles import RoleRecord, RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.model_runtime import RoleAwareProvider
from proactive_v2.config import ProactiveStrategiesConfig
from proactive_v2.config_loader import load_proactive_config
from proactive_v2.loop import ProactiveLoop
from proactive_v2.preferences import load_proactive_preferences
from proactive_v2.state import ProactiveStateStore
from session.manager import SessionManager
from shiori_sdk.core.proactive_host import ProactiveHost
from shiori_sdk.core.sessions import Presence

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from core.memory.runtime import MemoryRuntime

logger = logging.getLogger(__name__)


def assemble_generation_proactive(
    plugins: Mapping[str, Any],
    *,
    affection: AffectionGetter,
    event_bus: EventBus,
) -> tuple[
    ProactiveStrategiesConfig, list[ProactiveGate], SceneFollowupSubscription | None
]:
    """Scene and relationship motives for one runtime generation.

    The switches are this generation's ``[plugins.proactive]`` table. The
    motives and the scene subscription stay on the generation: an unpublished
    candidate must not consume the published generation's scene events, and a
    generation that is draining keeps its own bus. The tick that evaluates
    the motives enters through ``PROACTIVE_HOST``.
    """
    preferences = load_proactive_preferences(plugins)
    motives: list[ProactiveGate] = []
    if preferences.scene_followup:
        motives.append(SceneFollowupStrategy(affection))
    if preferences.relationship:
        motives.append(RelationshipStrategy(affection))
    subscription = (
        SceneFollowupSubscription(event_bus, affection)
        if preferences.scene_followup
        else None
    )
    return preferences, motives, subscription


def build_proactive_runtime(
    config: Config,
    workspace: Path,
    *,
    session_manager: SessionManager,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    push_tool: MessagePushTool,
    memory_store: "MemoryRuntime | None",
    presence: Presence,
    agent_loop: AgentLoop,
    kernel: KernelSource,
    proactive_motives: list[ProactiveGate] | None = None,
    event_bus: "EventBus | None" = None,
    provider_consumer: Callable[[LLMProvider], None] | None = None,
    proactive_host: ProactiveHost,
    group_environment: GroupEnvironment,
) -> tuple[list, dict[str, ProactiveLoop]]:
    """Builds one proactive loop per enabled role.

    Ticks, the role prompt, the passive-busy check, target reads and the
    model, tools and delivery a tick uses go through ``proactive_host``
    (``PROACTIVE_HOST``). ``group_environment`` is the runtime's shared group
    environment layer (#497); the port reads that same object for recent
    external activity.
    """
    tasks: list = []
    roles = [
        role for role in RoleStore(workspace).list_roles() if role.proactive.enabled
    ]
    if not roles:
        return tasks, {}

    # 2. 为每个角色创建独立配置、状态与 agent loop。
    proactive_provider = thinking_disabled_provider(config, provider)
    if provider_consumer is not None and proactive_provider is not provider:
        provider_consumer(proactive_provider)
    loops: dict[str, ProactiveLoop] = {}
    role_runtime_registry = agent_loop.role_runtime_registry
    if role_runtime_registry is None:
        raise RuntimeError("主动任务需要 RoleRuntimeRegistry")
    role_store = role_runtime_registry.repository.store
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
            passive_busy_fn=_passive_busy(proactive_host, role.id),
            shared_tools=getattr(agent_loop, "tools", None),
            kernel=kernel,
            proactive_motives=proactive_motives,
            event_bus=event_bus,
            role_prompt_fn=_role_prompt(proactive_host, role.id),
            tick_dispatcher=_tick_through_port(proactive_host, role.id),
            proactive_host=proactive_host,
            role_store=role_store,
            group_environment=group_environment,
        )
        loops[role.id] = loop
        tasks.append(loop.run())
    return tasks, loops


def _tick_through_port(host: ProactiveHost, role_id: str):
    """One role's tick, entered through ``PROACTIVE_HOST.run_tick``.

    The port pins the generation, opens the role's desktop thread and
    activates the chat model. A tick starts before its delivery target is
    chosen, so that thread is ``role:<id>``.
    """

    async def dispatch(operation):
        return await host.run_tick(role_id, operation)

    return dispatch


def _role_prompt(host: ProactiveHost, role_id: str):
    """The role prompt, read through ``PROACTIVE_HOST.compile_role_prompt``."""

    def resolve() -> str:
        return host.compile_role_prompt(role_id)

    return resolve


def _passive_busy(host: ProactiveHost, role_id: str):
    """Whether a passive turn holds this role's session.

    The pipeline passes the role session key. The port names the role; this
    loop serves that role, whose session is ``role:<id>``.
    """

    def busy(_session_key: str) -> bool:
        return host.passive_turn_busy(role_id)

    return busy


def _build_role_proactive_config(role: RoleRecord):
    """Builds the runtime proactive config from one authoritative role snapshot."""
    proactive = role.proactive
    agent = dict(getattr(proactive, "agent", {}) or {})
    agent.pop("model", None)
    # Delivery targets come from the role's candidate sessions, chosen per
    # message; the config only names the role it serves.
    return load_proactive_config(
        {
            "enabled": proactive.enabled,
            "profile": str(getattr(proactive, "profile", "daily") or "daily"),
            "overrides": dict(getattr(proactive, "overrides", {}) or {}),
            "agent": agent,
            "drift": dict(getattr(proactive, "drift", {}) or {}),
        },
        role_id=role.id,
    )
