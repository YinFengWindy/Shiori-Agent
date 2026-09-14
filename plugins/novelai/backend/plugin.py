"""novelai 插件装配：生图工具、自动 CG、桥接 RPC 与配置全部收拢在这里。

v2 插件（issue #180）：不再继承旧 ``Plugin`` ABC，改为 ``setup(ctx)`` 一次性
装配。``on_tool_pre`` / ``on_tool_result`` / ``on_after_reasoning`` 三个旧装饰器
底层都只是把处理函数登记进事件总线（见 ``agent.plugin_host.legacy``），
v2 下用 ``ctx.events.on`` / ``ctx.tool_hooks.add_handler`` 直接登记，行为完全
等价，只是登记方式从"扫描装饰器元数据"变成"setup() 里显式调用"。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, cast

from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterToolResultCtx,
)
from bus.events_lifecycle import SceneObservationCommitted
from core.net.http import get_default_http_requester
from core.roles.store import RoleStore

from .auto_cg import AutoCgPolicy
from .auto_cg_controller import AutoCgController
from .client import NovelAIClient
from .config import NovelAIConfig
from .models import NovelAISettings
from .prompt_tags import PromptTagStore
from .rpc import NovelAIRpcHandlers
from .service import NovelAIService
from .store import NovelAIStore
from .tool import GenerateImageTool

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

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

    async def attach_generated_media(self, ctx: AfterReasoningCtx) -> AfterReasoningCtx:
        media = self._pending_media.pop(ctx.session_key, [])
        if media:
            ctx.media.extend(media)
        return ctx


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 novelai：生图服务层、工具、自动 CG、桥接 RPC。"""

    workspace = ctx.workspace
    if workspace is None:
        raise RuntimeError("NovelAI 插件需要 workspace")
    settings = _load_settings(ctx)
    role_store = RoleStore(workspace)
    novelai_store = NovelAIStore(workspace)
    prompt_tag_store = PromptTagStore(workspace)
    service = NovelAIService(
        settings=settings,
        client=NovelAIClient(
            get_default_http_requester("external_default"),
            settings,
        ),
        store=novelai_store,
        role_store=role_store,
        workspace=workspace,
        prompt_tag_store=prompt_tag_store,
    )
    tool = GenerateImageTool(
        service,
        context_provider=ctx.tools.get_context,
    )
    # Dependent plugins receive this generation's NovelAI API, never a host image-provider abstraction.
    ctx.expose(tool)
    ctx.tools.register(
        tool,
        risk="external-side-effect",
        always_on=True,
        search_hint="生图 生成图片 NovelAI 立绘 场景图",
    )

    auto_cg = AutoCgPolicy(ctx.kv)
    auto_cg_controller = AutoCgController(
        role_store=role_store,
        policy=auto_cg,
        session_manager=ctx.session_manager,
        generate_tool=tool,
        tool_registry=ctx.tools,
        light_provider=ctx.light_provider,
        light_model=ctx.light_model,
    )
    # 宿主先停用并退订所有事件，再清理资源，与这两项的登记先后无关。
    # terminate 仍负责取消并等待已经启动的生成任务。
    ctx.effect("auto_cg_controller", auto_cg_controller.terminate)
    ctx.events.on(SceneObservationCommitted, auto_cg_controller.schedule)
    ctx.scene_observations.request(
        lambda role: bool(role.runtime_config.get("auto_scene_cg_enabled"))
    )

    ctx.tool_hooks.add_handler(
        lambda event: auto_cg.guard(event.session_key, event.arguments),
        tool_name_filter="generate_image",
        handler_name="guard_auto_cg",
    )

    tracker = _MediaTracker(auto_cg)
    ctx.events.on(AfterToolResultCtx, tracker.collect_generated_media)
    ctx.events.on(AfterToolResultCtx, tracker.consume_pushed_media)
    ctx.events.on(AfterReasoningCtx, tracker.attach_generated_media)

    _register_rpc(
        ctx,
        NovelAIRpcHandlers(
            novelai_service=service,
            novelai_store=novelai_store,
            prompt_tag_store=prompt_tag_store,
            session_manager=ctx.session_manager,
            relationship_runtime=ctx.relationship_runtime,
        ),
    )


def _load_settings(ctx: "PluginRuntimeContext") -> NovelAISettings:
    """Builds the runtime settings dataclass from the validated ``[plugins.novelai]`` config.

    ``ctx.config`` only carries the *overridden* raw values; running them
    through ``NovelAIConfig`` fills in the rest from its declared defaults
    (identical to ``NovelAISettings``'s own), so this is the single place that
    resolves "declared override + default" instead of duplicating defaults.
    """

    config = NovelAIConfig.model_validate(ctx.config.as_dict())
    return NovelAISettings(**config.model_dump())


def _register_rpc(ctx: "PluginRuntimeContext", handlers: NovelAIRpcHandlers) -> None:
    # Local import: RPC concurrency policy types live in the desktop bridge;
    # deferring the import to setup() keeps the plugin's module-load path from
    # requiring the desktop bridge dependency chain (matches the discipline
    # documented on agent.plugin_host.capabilities.RpcCapability.register).
    from desktop_bridge.method_policy import Concurrency

    ctx.rpc.register("generate", handlers.generate, concurrency=Concurrency.INTEGRATION)
    ctx.rpc.register(
        "regenerateMessageMedia",
        handlers.regenerate_message_media,
        concurrency=Concurrency.INTEGRATION,
    )
    ctx.rpc.register("history", handlers.history, concurrency=Concurrency.READ_ONLY)
    ctx.rpc.register(
        "prompt_tags.list",
        handlers.prompt_tags_list,
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register("prompt_tags.upsert", handlers.prompt_tags_upsert)
    ctx.rpc.register("prompt_tags.delete", handlers.prompt_tags_delete)


def _safe_json(text: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}
