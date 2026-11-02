"""Proactive loops: one process resource, rebound by each published generation.

Role loops start in ``PROCESS_RESOURCES.on_published``, not during setup of a
candidate generation, and follow role creation and deletion from then on.
Scene follow-up demand is ``SCENE.request``. The scene subscription that
writes decisions into affection also starts at publication.
"""

from __future__ import annotations

import logging
from functools import partial

from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.conversation import CONVERSATION, PromptRendering
from shiori_sdk.core.markdown_memory import MARKDOWN_MEMORY
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.models import MAIN_MODEL
from shiori_sdk.core.proactive_host import PROACTIVE_HOST
from shiori_sdk.core.reply_policy import REPLY_POLICY
from shiori_sdk.core.scene import SCENE
from shiori_sdk.core.services import (
    CONFIG,
    EVENTS,
    PROCESS_RESOURCES,
    PROCESSES,
    ROLES,
    RPC,
    WORKSPACE,
)
from shiori_sdk.core.sessions import SESSIONS
from shiori_sdk.role_events import RoleCreated, RoleDeleted
from shiori_sdk.roles import Roles, RoleView
from shiori_sdk.runtime import PluginRuntimeContext

from .plugin_config import ProactivePluginConfig
from .role_prompt import append_proactive_prompt
from .role_settings import ProactiveRoleSettings
from .skill_prompt import append_skill_prompt
from .service import ProactiveBinding, ProactiveService
from .turn.scene_subscription import SceneFollowupSubscription

logger = logging.getLogger(__name__)

# Bump when the retained service's methods change incompatibly.
_RESOURCE_KEY = "proactive-v2"


def _switch_on(roles: Roles, role: RoleView) -> bool:
    settings = roles.plugin_settings(role.id, "proactive").read()
    return bool(settings.get("enabled"))


async def setup(ctx: PluginRuntimeContext) -> None:
    """Attaches this generation. Role loops start once it is published."""
    config = ProactivePluginConfig.model_validate(ctx.require(CONFIG).as_dict())
    events = ctx.require(EVENTS)
    roles = ctx.require(ROLES)
    ctx.on(
        PromptRendering,
        partial(append_skill_prompt, workspace=ctx.require(WORKSPACE)),
    )
    ctx.on(
        PromptRendering,
        partial(append_proactive_prompt, workspace=ctx.require(WORKSPACE), roles=roles),
    )
    settings = ProactiveRoleSettings(roles)
    ctx.effect(
        "proactive.role_settings",
        roles.extensions.register("proactive", settings.reject_draft, settings.project),
    )
    rpc = ctx.require(RPC)
    rpc.register("settings_set", settings.set)
    scene = ctx.get(SCENE)
    if scene is not None and config.scene_followup:
        ctx.effect(
            "proactive.scene_demand",
            scene.request(lambda role: _switch_on(roles, role)),
        )

    resources = ctx.require(PROCESS_RESOURCES)
    service: ProactiveService | None = None
    if ctx.get(MAIN_MODEL) is None:
        # No chat model: do not acquire the resource, so a running loop stops
        # when this generation is published. Scene follow-up still subscribes.
        logger.info("[proactive] 没有模型注册，主动循环不运行")
    else:
        service = resources.acquire(_RESOURCE_KEY, ProactiveService)
        policy = ctx.get(REPLY_POLICY)
        binding = ProactiveBinding(
            host=ctx.require(PROACTIVE_HOST),
            conversation=ctx.require(CONVERSATION),
            roles=roles,
            processes=ctx.require(PROCESSES),
            workspace=ctx.require(WORKSPACE),
            presence=ctx.require(SESSIONS).presence,
            markdown=ctx.require(MARKDOWN_MEMORY),
            memory_engine=ctx.get(MEMORY_ENGINE),
            scene_followup=config.scene_followup,
            relationship=config.relationship,
            affection=ctx.get(AFFECTION),
            draft_prompt=(
                (lambda: policy.draft_prompt())
                if policy is not None
                else (lambda: None)
            ),
            is_active=lambda: resources.active,
        )
        ctx.effect("proactive.binding", service.attach(binding))

    def on_published() -> None:
        if service is not None:
            service.published()

            def _roles(_event: object) -> None:
                service.on_roles_changed()

            events.on(RoleCreated, _roles)
            events.on(RoleDeleted, _roles)
        if config.scene_followup:
            subscription = SceneFollowupSubscription(events, lambda: ctx.get(AFFECTION))
            subscription.start()
            ctx.effect("proactive.scene_followup", subscription.stop)

    ctx.effect("proactive.publication", resources.on_published(on_published))
