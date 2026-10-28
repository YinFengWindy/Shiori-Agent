"""novelai 插件装配：生图工具、自动 CG、桥接 RPC 与配置全部收拢在这里。

v2 插件（issue #180）：不再继承旧 ``Plugin`` ABC，改为 ``setup(ctx)`` 一次性
装配。生图前的自动 CG 守卫与生图结果的收集挂在工具事件 ``ToolCalling`` /
``ToolCalled`` 上，附图挂在 ``ReasoningFinished`` 上（#902）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from shiori_sdk.core.conversation import ReasoningFinished
from shiori_sdk.core.tools import ToolCalled, ToolCalling, ToolVeto
from shiori_sdk.role_events import RoleDeleted, SceneObservationCommitted
from shiori_sdk.rpc import Concurrency
from shiori_sdk.core.services import (
    BACKGROUND,
    CONFIG,
    EVENTS,
    HTTP,
    KV,
    LIGHT_MODEL,
    LIGHT_PROVIDER,
    ROLES,
    RPC,
    SCENE_OBSERVATIONS,
    SESSION_STORE,
    TOOLS,
    WORKSPACE,
)

from .auto_cg import AutoCgPolicy
from .api import ImageGenerationAPI
from .auto_cg_controller import AutoCgController
from .client import NovelAIClient
from .config import NovelAIConfig
from .models import NovelAISettings
from .prompt_tags import PromptTagStore
from .rpc import NovelAIRpcHandlers
from .role_state import NovelAIRoleState
from .role_settings_rpc import NovelAIRoleSettingsRpc
from .service import NovelAIService
from .store import NovelAIStore
from .tool import GenerateImageTool

if TYPE_CHECKING:
    from shiori_sdk.runtime import PluginRuntimeContext

logger = logging.getLogger(__name__)


class _MediaTracker:
    """Attaches media produced by ``generate_image`` to the reply that follows it.

    Ported unchanged from the legacy ``NovelAIPlugin``: a tool result can be
    produced well before ``after_reasoning`` runs, and a subsequent
    ``message_push`` may already have delivered the same media (automatic
    scene CG), so pending media is tracked per session and consumed once by
    whichever happens first.
    """

    def __init__(self, auto_cg: AutoCgPolicy) -> None:
        self._auto_cg = auto_cg
        self._pending_media: dict[str, list[str]] = {}

    async def track(self, event: ToolCalled) -> ToolCalled:
        """Passes the result on unchanged; only passive turns' calls are tracked."""
        # Only a passive turn's reply picks the media up (``attach_generated_media``).
        if event.source == "passive":
            self.collect_generated_media(event)
            self.consume_pushed_media(event)
        return event

    def collect_generated_media(self, event: ToolCalled) -> None:
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

    def consume_pushed_media(self, event: ToolCalled) -> None:
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

    async def attach_generated_media(
        self, event: ReasoningFinished
    ) -> ReasoningFinished:
        media = self._pending_media.pop(event.session_key, [])
        if not media:
            return event
        return replace(event, media=(*event.media, *media))


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 novelai：生图服务层、工具、自动 CG、桥接 RPC。"""

    workspace = ctx.require(WORKSPACE)
    settings = _load_settings(ctx)
    role_store = ctx.require(ROLES)
    role_state = NovelAIRoleState(role_store)
    role_state.reconcile()
    ctx.require(EVENTS).on(RoleDeleted, role_state.on_role_deleted)
    ctx.effect(
        "role_settings",
        role_store.extensions.register(
            "novelai", NovelAIRoleState.write_draft, NovelAIRoleState.project
        ),
    )
    role_settings = NovelAIRoleSettingsRpc(role_state)
    ctx.require(RPC).register(
        "role_settings.get", role_settings.get, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register("role_settings.set", role_settings.set)
    novelai_store = NovelAIStore(
        workspace, original_media=ctx.require(SESSION_STORE).original_media_path
    )
    prompt_tag_store = PromptTagStore(workspace)
    service = NovelAIService(
        settings=settings,
        client=NovelAIClient(
            ctx.require(HTTP),
            settings,
        ),
        store=novelai_store,
        role_store=role_store,
        workspace=workspace,
        prompt_tag_store=prompt_tag_store,
    )
    tool = GenerateImageTool(
        service,
        context_provider=ctx.require(TOOLS).get_context,
    )
    # Dependent plugins receive this generation's NovelAI API, never a host image-provider abstraction.
    api: ImageGenerationAPI = tool
    ctx.expose(api)
    ctx.require(TOOLS).register(
        tool,
        risk="external-side-effect",
        always_on=True,
        search_hint="生图 生成图片 NovelAI 立绘 场景图",
        # 群聊等外部上下文里的其他人也能让角色生图（#489）。
        external_allowed=True,
    )

    auto_cg = AutoCgPolicy(ctx.require(KV))
    auto_cg_controller = AutoCgController(
        role_store=role_store,
        policy=auto_cg,
        background=ctx.require(BACKGROUND),
        session_manager=ctx.require(SESSION_STORE),
        generate_tool=tool,
        tool_registry=ctx.require(TOOLS),
        light_provider=ctx.require(LIGHT_PROVIDER),
        light_model=ctx.require(LIGHT_MODEL),
    )
    # 宿主先停用并退订所有事件，再清理资源，与这两项的登记先后无关。
    # terminate 仍负责取消并等待已经启动的生成任务。
    ctx.effect("auto_cg_controller", auto_cg_controller.terminate)
    ctx.require(EVENTS).on(SceneObservationCommitted, auto_cg_controller.schedule)
    ctx.require(SCENE_OBSERVATIONS).request(lambda role: role_state.enabled(role.id))

    async def guard_auto_cg(event: ToolCalling) -> ToolCalling | ToolVeto:
        if event.tool_name != "generate_image":
            return event
        prepared = auto_cg.guard(event.session_key, dict(event.arguments))
        if prepared is None:
            return event
        if isinstance(prepared, ToolVeto):
            return prepared
        return replace(event, arguments=prepared)

    ctx.on(ToolCalling, guard_auto_cg)

    tracker = _MediaTracker(auto_cg)
    ctx.on(ToolCalled, tracker.track)
    ctx.on(ReasoningFinished, tracker.attach_generated_media)

    _register_rpc(
        ctx,
        NovelAIRpcHandlers(
            novelai_service=service,
            novelai_store=novelai_store,
            prompt_tag_store=prompt_tag_store,
            session_manager=ctx.require(SESSION_STORE),
        ),
    )


def _load_settings(ctx: "PluginRuntimeContext") -> NovelAISettings:
    """Builds the runtime settings dataclass from the validated ``[plugins.novelai]`` config.

    ``ctx.require(CONFIG)`` only carries the *overridden* raw values; running them
    through ``NovelAIConfig`` fills in the rest from its declared defaults
    (identical to ``NovelAISettings``'s own), so this is the single place that
    resolves "declared override + default" instead of duplicating defaults.
    """

    config = NovelAIConfig.model_validate(ctx.require(CONFIG).as_dict())
    return NovelAISettings(**config.model_dump())


def _register_rpc(ctx: "PluginRuntimeContext", handlers: NovelAIRpcHandlers) -> None:
    ctx.require(RPC).register(
        "generate", handlers.generate, concurrency=Concurrency.INTEGRATION
    )
    ctx.require(RPC).register(
        "regenerateMessageMedia",
        handlers.regenerate_message_media,
        concurrency=Concurrency.INTEGRATION,
    )
    ctx.require(RPC).register(
        "history", handlers.history, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register(
        "status", handlers.status, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register(
        "prompt_tags.list",
        handlers.prompt_tags_list,
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register("prompt_tags.upsert", handlers.prompt_tags_upsert)
    ctx.require(RPC).register("prompt_tags.delete", handlers.prompt_tags_delete)


def _safe_json(text: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}
