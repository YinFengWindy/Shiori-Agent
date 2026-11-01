from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.config_models import Config
from agent.core.prompt_block import build_role_affection_prompt
from agent.core.proactive_turn.gates import ProactiveGate
from agent.core.proactive_turn.scene_subscription import SceneFollowupSubscription
from agent.core.proactive_turn.strategies import (
    RelationshipStrategy,
    SceneFollowupStrategy,
)
from core.roles import RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.plugin_capability import HostRoles
from proactive_v2.config import ProactiveStrategiesConfig
from proactive_v2.config_loader import load_proactive_config
from proactive_v2.loop import ProactiveLoop
from proactive_v2.preferences import load_proactive_preferences
from proactive_v2.state import ProactiveStateStore
from session.manager import SessionManager
from shiori_sdk.core.conversation import Conversation
from shiori_sdk.core.proactive_host import ProactiveHost
from shiori_sdk.core.sessions import Presence
from shiori_sdk.roles import Roles

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
    memory_store: "MemoryRuntime | None",
    presence: Presence,
    role_store: RoleStore,
    proactive_motives: list[ProactiveGate] | None = None,
    proactive_host: ProactiveHost,
    conversation: Conversation,
) -> tuple[list, dict[str, ProactiveLoop]]:
    """Builds one proactive loop per enabled role.

    Ticks, the role prompt, the passive-busy check, target reads and the
    model, tools and delivery a tick uses go through ``proactive_host``
    (``PROACTIVE_HOST``). ``conversation`` is this generation's
    ``CONVERSATION``: the tick reads its reply stamp there. Which roles are
    enabled and their settings are each role's ``proactive`` namespace on
    ``ROLES`` over ``role_store``, the generation's shared store.
    """
    tasks: list = []
    roles: Roles = HostRoles(role_store)
    enabled = [
        (role.id, settings)
        for role in roles.list_roles()
        if (settings := roles.plugin_settings(role.id, "proactive").read()).get(
            "enabled"
        )
    ]
    if not enabled:
        return tasks, {}

    # 2. 为每个角色创建独立配置、状态与 agent loop。
    loops: dict[str, ProactiveLoop] = {}
    for role_id, settings in enabled:
        loop = ProactiveLoop(
            session_manager,
            _build_role_proactive_config(role_id, settings),
            proactive_host=proactive_host,
            conversation=conversation,
            roles=roles,
            role_prompt_fn=_role_prompt(proactive_host, role_id),
            max_tokens=config.max_tokens,
            state_store=ProactiveStateStore(
                workspace / "roles" / role_id / "proactive.db"
            ),
            memory_store=memory_store,
            presence=presence,
            passive_busy_fn=_passive_busy(proactive_host, role_id),
            proactive_motives=proactive_motives,
            tick_dispatcher=_tick_through_port(proactive_host, role_id),
            # Proactive and drift turns always address the user (the user
            # context), so the affection block needs no visibility check.
            affection_prompt_fn=partial(
                build_role_affection_prompt, role_id, role_store
            ),
        )
        loops[role_id] = loop
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


def _build_role_proactive_config(role_id: str, settings: Mapping[str, object]):
    """Builds the runtime proactive config from the role's ``proactive`` settings."""
    agent = dict(_mapping(settings.get("agent")))
    agent.pop("model", None)
    # Delivery targets come from the role's candidate sessions, chosen per
    # message; the config only names the role it serves.
    return load_proactive_config(
        {
            "enabled": bool(settings.get("enabled")),
            "profile": str(settings.get("profile") or "daily"),
            "overrides": dict(_mapping(settings.get("overrides"))),
            "agent": agent,
            "drift": dict(_mapping(settings.get("drift"))),
        },
        role_id=role_id,
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}
