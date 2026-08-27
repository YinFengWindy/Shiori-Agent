from __future__ import annotations

import logging

from agent.lifecycle.types import AfterTurnCtx, BeforeTurnCtx
from agent.plugins import Plugin, on_after_turn, on_before_turn
from bus.events_lifecycle import ProactiveMessageCommitted
from core.roles.store import RoleStore
from plugins.scene_awareness.controller import SceneAwarenessController

logger = logging.getLogger(__name__)


class SceneAwarenessPlugin(Plugin):
    """Observe completed role turns and publish shared scene decisions."""

    name = "scene_awareness"

    async def initialize(self) -> None:
        workspace = self.context.workspace
        if workspace is None:
            raise RuntimeError("场景观察插件需要 workspace")
        self._controller = SceneAwarenessController(
            role_store=RoleStore(workspace),
            session_manager=self.context.session_manager,
            event_bus=self.context.event_bus,
            kv_store=self.context.kv_store,
            light_provider=self.context.light_provider,
            light_model=self.context.light_model,
        )
        self._proactive_handler = self._handle_proactive_message
        self.context.event_bus.on(
            ProactiveMessageCommitted,
            self._proactive_handler,
        )
        if self.context.light_provider is None or not self.context.light_model.strip():
            logger.warning("场景观察缺少 light_model provider，后台判定已禁用")

    @property
    def scene_tasks(self):
        """Return a snapshot of in-flight scene observation tasks."""

        return self._controller.tasks

    @on_before_turn()
    async def capture_passive_turn(self, ctx: BeforeTurnCtx) -> BeforeTurnCtx:
        """Capture the passive turn before reasoning mutates its context."""

        self._controller.capture_passive_turn(ctx)
        return ctx

    @on_after_turn()
    async def schedule_passive_turn(self, ctx: AfterTurnCtx) -> None:
        """Schedule observation after a passive text turn completes."""

        self._controller.schedule_passive_turn(ctx)

    def _handle_proactive_message(self, event: ProactiveMessageCommitted) -> None:
        self._controller.schedule_proactive_turn(event)

    async def terminate(self) -> None:
        handler = getattr(self, "_proactive_handler", None)
        if handler is not None:
            self.context.event_bus.off(ProactiveMessageCommitted, handler)
        controller = getattr(self, "_controller", None)
        if controller is not None:
            await controller.terminate()
