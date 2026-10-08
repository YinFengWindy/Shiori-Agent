"""Assembles the live engine from the plugin context and registers its RPCs."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import TYPE_CHECKING

from shiori_sdk.role_events import RoleDeleted

from .bilibili_live_api import BilibiliLiveApi
from .bilibili_live_source import BilibiliDanmakuSource
from .bilibili_login import BilibiliLoginService
from .live_clock import SystemClock
from .live_config import LiveConfigStore
from .live_engine import LiveEngine
from .live_output import LiveReplyOutput
from .live_rpc import register_live_rpc
from .live_session import LiveSessionDeps
from .pet_state import RolePetStateStore

if TYPE_CHECKING:
    from shiori_sdk.plugin_services import ServicePluginContext


def setup_live_engine(
    ctx: "ServicePluginContext",
    login: BilibiliLoginService,
    output: LiveReplyOutput,
) -> LiveEngine:
    """Build the engine on real Bilibili clients; disable ends its run."""
    api = BilibiliLiveApi()
    configs = LiveConfigStore(ctx.workspace)

    def spawn(work: Coroutine[object, object, None], name: str):
        return ctx.background.spawn(work, name=name)

    engine = LiveEngine(
        roles=ctx.roles,
        configs=configs,
        api=api,
        deps=LiveSessionDeps(
            source=BilibiliDanmakuSource(api),
            turns=ctx.external_turns,
            output=output,
            credentials=login.require_credentials,
            still_bound=RolePetStateStore(ctx.roles).is_enabled,
            clock=SystemClock(),
            spawn=spawn,
        ),
    )
    engine.prune_deleted_roles()
    ctx.events.on(RoleDeleted, engine.on_role_deleted)
    ctx.effect("live_outcome_route", output.subscribe(engine.outcome))
    ctx.effect("live_engine", engine.shutdown)
    register_live_rpc(ctx.rpc, engine, configs)
    return engine
