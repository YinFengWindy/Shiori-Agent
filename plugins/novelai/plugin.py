from __future__ import annotations

import json
from typing import Any, cast

from agent.lifecycle.types import AfterReasoningCtx, AfterToolResultCtx
from agent.plugins import Plugin, on_after_reasoning, on_tool_result
from agent.tools.image_generate import GenerateImageTool
from core.integrations.novelai.client import NovelAIClient
from core.integrations.novelai.models import NovelAISettings
from core.integrations.novelai.service import NovelAIService
from core.integrations.novelai.store import NovelAIStore
from core.net.http import get_default_http_requester
from core.roles.store import RoleStore


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
        self._pending_media: dict[str, list[str]] = {}
        self.context.tool_registry.register(
            self._tool,
            risk="external-side-effect",
            always_on=True,
            search_hint="生图 生成图片 NovelAI 立绘 场景图",
            source_type="plugin",
            source_name=self.name,
        )

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
        media = [str(item).strip() for item in raw_paths if str(item).strip()]
        if not media:
            return
        self._pending_media.setdefault(event.session_key, []).extend(media)

    @on_tool_result()
    async def consume_pushed_media(self, event: AfterToolResultCtx) -> None:
        if event.tool_name != "message_push" or event.status != "success":
            return
        sent_paths = {
            str(event.arguments.get(key) or "").strip()
            for key in ("image", "file")
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
            self._pending_media.pop(event.session_key, None)

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
