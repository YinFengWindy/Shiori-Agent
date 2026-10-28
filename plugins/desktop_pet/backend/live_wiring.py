"""Assembles the live engine from the plugin context and registers its RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.core.services import (
    BACKGROUND,
    EVENTS,
    EXTERNAL_TURNS,
    ROLES,
    RPC,
    WORKSPACE,
)

from .bilibili_live_api import BilibiliLiveApi
from .bilibili_live_source import BilibiliDanmakuSource
from .bilibili_login import BilibiliLoginService
from .live_clock import SystemClock
from .live_config import LiveConfigStore
from .live_engine import LiveEngine
from .live_gate import LiveStartGate
from .live_output import LiveReplyOutput
from .live_rpc import register_live_rpc
from .live_session import LiveSessionDeps
from .pet_state import RolePetStateStore
from .voice_preferences import VoicePreferencesStore

if TYPE_CHECKING:
    from shiori_sdk.plugin_services import ServicePluginContext


def setup_live_engine(
    ctx: "ServicePluginContext",
    login: BilibiliLoginService,
    output: LiveReplyOutput,
) -> LiveEngine:
    """Build the engine on real Bilibili clients; disable ends its run."""
    api = BilibiliLiveApi()
    configs = LiveConfigStore(ctx.require(WORKSPACE))
    is_pet_role = RolePetStateStore(ctx.require(ROLES)).is_enabled
    engine = LiveEngine(
        roles=ctx.require(ROLES),
        gate=LiveStartGate(
            roles=ctx.require(ROLES),
            configs=configs,
            voice=VoicePreferencesStore(ctx.require(WORKSPACE)),
            is_pet_role=is_pet_role,
            credentials=login.require_credentials,
        ),
        configs=configs,
        api=api,
        deps=LiveSessionDeps(
            source=BilibiliDanmakuSource(api),
            turns=ctx.require(EXTERNAL_TURNS),
            output=output,
            credentials=login.require_credentials,
            still_bound=is_pet_role,
            clock=SystemClock(),
            spawn=ctx.require(BACKGROUND).spawn,
        ),
    )
    engine.prune_deleted_roles()
    ctx.require(EVENTS).on(RoleDeleted, engine.on_role_deleted)
    ctx.effect("live_outcome_route", output.subscribe(engine.outcome))
    ctx.effect("live_engine", engine.shutdown)
    register_live_rpc(ctx.require(RPC), engine, configs)
    return engine
