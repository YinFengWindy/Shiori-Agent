from __future__ import annotations

import json
import logging
from typing import Any, cast

from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterToolResultCtx,
    PreToolCtx,
)
from agent.plugins import (
    Plugin,
    on_after_reasoning,
    on_tool_pre,
    on_tool_result,
)
from agent.tools.image_generate import GenerateImageTool
from bus.events_lifecycle import SceneObservationCommitted
from core.integrations.novelai.client import NovelAIClient
from core.integrations.novelai.models import NovelAISettings
from core.integrations.novelai.service import NovelAIService
from core.integrations.novelai.store import NovelAIStore
from core.net.http import get_default_http_requester
from core.roles.store import RoleStore
from plugins.novelai.auto_cg import AutoCgPolicy
from plugins.novelai.auto_cg_controller import AutoCgController

logger = logging.getLogger(__name__)


class NovelAIPlugin(Plugin):
    """Register the NovelAI image generation tool and attach generated media."""

    name = "novelai"

    async def initialize(self) -> None:
        workspace = self.context.workspace
        if workspace is None:
            raise RuntimeError("NovelAI 插件需要 workspace")
        app_config = self.context.app_config
        settings = cast(
            NovelAISettings,
            getattr(app_config, "novelai", NovelAISettings()),
        )
        self._settings = settings
        role_store = RoleStore(workspace)
        service = NovelAIService(
            settings=settings,
            client=NovelAIClient(
                get_default_http_requester("external_default"),
                settings,
            ),
            store=NovelAIStore(workspace),
            role_store=role_store,
            workspace=workspace,
        )
        self._tool = GenerateImageTool(
            service,
            context_provider=self.context.tool_registry.get_context,
        )
        self._auto_cg = AutoCgPolicy(self.context.kv_store)
        self._auto_cg_controller = AutoCgController(
            settings=settings,
            role_store=role_store,
            policy=self._auto_cg,
            session_manager=self.context.session_manager,
            generate_tool=self._tool,
            tool_registry=self.context.tool_registry,
        )
        self._scene_handler = self._handle_scene_observation
        self.context.event_bus.on(SceneObservationCommitted, self._scene_handler)
        self._pending_media: dict[str, list[str]] = {}
        self.context.tool_registry.register(
            self._tool,
            risk="external-side-effect",
            always_on=True,
            search_hint="生图 生成图片 NovelAI 立绘 场景图",
            source_type="plugin",
            source_name=self.name,
        )

    @property
    def _auto_cg_tasks(self) -> dict[str, Any]:
        """Backward-compatible view of controller tasks for integrations/tests."""

        return self._auto_cg_controller.tasks

    def _handle_scene_observation(self, event: SceneObservationCommitted) -> None:
        self._auto_cg_controller.schedule(event)

    @on_tool_pre(tool_name="generate_image")
    async def guard_auto_cg(
        self,
        event: PreToolCtx,
    ):
        """Enforce cooldown and scene deduplication before automatic CG calls."""

        return self._auto_cg.guard(event.session_key, event.arguments)

    async def terminate(self) -> None:
        handler = getattr(self, "_scene_handler", None)
        if handler is not None:
            self.context.event_bus.off(SceneObservationCommitted, handler)
        controller = getattr(self, "_auto_cg_controller", None)
        if controller is not None:
            await controller.terminate()
        tool = getattr(self, "_tool", None)
        if tool is not None:
            self.context.tool_registry.unregister(tool.name)

    @on_tool_result()
    async def collect_generated_media(self, event: AfterToolResultCtx) -> None:
        if event.tool_name != "generate_image" or event.status != "success":
            return
        payload = _safe_json(event.result)
        raw_paths = payload.get("output_paths")
        if not isinstance(raw_paths, list):
            return
        paths = cast(list[Any], raw_paths)
        media = [str(item).strip() for item in paths if str(item).strip()]
        if not media:
            return
        if str(event.arguments.get("intent") or "").strip() == "scene_cg":
            self._auto_cg.record_success(
                event.session_key,
                event.arguments.get("visual_key") or event.arguments.get("scene_key"),
            )
        self._pending_media.setdefault(event.session_key, []).extend(media)

    @on_tool_result()
    async def consume_pushed_media(self, event: AfterToolResultCtx) -> None:
        if event.tool_name != "message_push" or event.status != "success":
            return
        sent_paths = {
            str(event.arguments.get(key) or "").strip() for key in ("image", "file")
        }
        sent_paths.discard("")
        if not sent_paths:
            return
        pending = self._pending_media.get(event.session_key)
        if not pending:
            return
        remaining = [path for path in pending if path not in sent_paths]
        if remaining:
            self._pending_media[event.session_key] = remaining
        else:
            _ = self._pending_media.pop(event.session_key, None)

    @on_after_reasoning()
    async def attach_generated_media(self, ctx: AfterReasoningCtx) -> AfterReasoningCtx:
        media = self._pending_media.pop(ctx.session_key, [])
        if media:
            ctx.media.extend(media)
        return ctx


def _safe_json(text: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}
