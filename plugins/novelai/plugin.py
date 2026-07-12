from __future__ import annotations

import json
from typing import Any, cast

from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterToolResultCtx,
    BeforeTurnCtx,
    PreToolCtx,
    PromptRenderCtx,
)
from agent.plugins import (
    Plugin,
    on_after_reasoning,
    on_before_turn,
    on_prompt_render,
    on_tool_pre,
    on_tool_result,
)
from agent.tools.image_generate import GenerateImageTool
from core.integrations.novelai.client import NovelAIClient
from core.integrations.novelai.models import NovelAISettings
from core.integrations.novelai.service import NovelAIService
from core.integrations.novelai.store import NovelAIStore
from core.net.http import get_default_http_requester
from core.roles.store import RoleStore
from plugins.novelai.auto_cg import AutoCgPolicy


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
        service = NovelAIService(
            settings=settings,
            client=NovelAIClient(
                get_default_http_requester("external_default"),
                settings,
            ),
            store=NovelAIStore(workspace),
            role_store=RoleStore(workspace),
            workspace=workspace,
        )
        self._tool = GenerateImageTool(service)
        self._auto_cg = AutoCgPolicy(self.context.kv_store)
        self._pending_media: dict[str, list[str]] = {}
        self.context.tool_registry.register(
            self._tool,
            risk="external-side-effect",
            always_on=True,
            search_hint="生图 生成图片 NovelAI 立绘 场景图",
            source_type="plugin",
            source_name=self.name,
        )

    @on_before_turn()
    async def advance_auto_cg_turn(self, ctx: BeforeTurnCtx) -> BeforeTurnCtx:
        """Advance the persisted user-turn counter for one conversation."""

        self._auto_cg.advance_turn(ctx.session_key)
        return ctx

    @on_prompt_render()
    async def inject_auto_cg_protocol(self, ctx: PromptRenderCtx) -> PromptRenderCtx:
        """Inject scene-aware CG guidance for active role conversations."""

        if not self._settings.enabled:
            return ctx
        role_id = str(ctx.session_metadata.get("role_id") or "").strip()
        if not role_id:
            return ctx
        runtime_config = ctx.session_metadata.get("role_runtime_config")
        if (
            not isinstance(runtime_config, dict)
            or not bool(runtime_config.get("auto_scene_cg_enabled"))
        ):
            return ctx
        ctx.system_sections_top.append(
            self._auto_cg.build_prompt_section(ctx.session_key)
        )
        return ctx

    @on_tool_pre(tool_name="generate_image")
    async def guard_auto_cg(
        self,
        event: PreToolCtx,
    ):
        """Enforce cooldown and scene deduplication before automatic CG calls."""

        return self._auto_cg.guard(event.session_key, event.arguments)

    async def terminate(self) -> None:
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
                event.arguments.get("scene_key"),
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
