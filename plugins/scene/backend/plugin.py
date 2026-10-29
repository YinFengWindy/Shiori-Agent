"""Scene observation: demand, intake and the light-model decision."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shiori_sdk.core.scene import SCENE, SCENE_HOST
from shiori_sdk.core.services import (
    BACKGROUND,
    CONFIG,
    EVENTS,
    LIGHT_MODEL,
    LIGHT_PROVIDER,
    ROLES,
    WORKSPACE,
)
from shiori_sdk.role_events import SceneObservationCommitted
from shiori_sdk.runtime import PluginRuntimeContext

from .config import SceneConfig
from .service import SceneService
from .state import SceneStateStore


async def setup(ctx: PluginRuntimeContext) -> None:
    """Provides ``SCENE``. Intake starts only when the host publishes the generation."""
    host = ctx.require(SCENE_HOST)
    background = ctx.require(BACKGROUND)
    events = ctx.require(EVENTS)
    light_provider = ctx.get(LIGHT_PROVIDER)
    light_model = ctx.get(LIGHT_MODEL)
    config = SceneConfig.model_validate(ctx.require(CONFIG).as_dict())
    service = SceneService(
        host=host,
        roles=ctx.require(ROLES),
        state=SceneStateStore(ctx.require(WORKSPACE), host.legacy_state_paths()),
        light_provider=light_provider,
        light_model=str(light_model or ""),
        spawn=lambda coro, name: background.spawn(coro, name=name),
        publish=_publish(events),
        events=events,
        observation_enabled=config.observation_enabled,
    )
    ctx.provide(SCENE, service)

    async def close() -> None:
        await service.close()

    ctx.effect("scene.close", close)


def _publish(
    events: object,
) -> Callable[[SceneObservationCommitted], Awaitable[None]]:
    """Fan the decision out so listeners do not block the observation task."""

    async def publish(event: SceneObservationCommitted) -> None:
        fanout = getattr(events, "fanout")
        await fanout(event)

    return publish
