from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol, cast

from bus.events_lifecycle import SceneObservationCommitted
from core.roles.store import RoleStore
from core.common.runtime_tasks import create_runtime_task

from .auto_cg import AutoCgPolicy
from .scene_prompt import prepare_scene_prompt
from .tool import GenerateImageTool

logger = logging.getLogger(__name__)

_MAX_GENERATION_RETRIES = 1
_REQUIRED_TRANSITIONS = {"started", "changed"}


class _ToolLookup(Protocol):
    """Structural type for the one thing this controller needs: tool lookup.

    Satisfied by both the raw ``ToolRegistry`` and the ``ToolsCapability``
    wrapper the v2 plugin runtime hands out (``ctx.tools``) — tests build the
    former directly, ``plugin.py`` passes the latter.
    """

    def get_tool(self, name: str) -> Any: ...


class AutoCgController:
    """Generate and deliver scene CG from shared scene observations."""

    def __init__(
        self,
        *,
        role_store: RoleStore,
        policy: AutoCgPolicy,
        session_manager: Any,
        generate_tool: GenerateImageTool,
        tool_registry: _ToolLookup,
        light_provider: Any = None,
        light_model: str = "",
        prompt_provider: Any = prepare_scene_prompt,
    ) -> None:
        self._light_provider = light_provider
        self._light_model = light_model
        self._prompt_provider = prompt_provider
        self._closed = False
        self._all_tasks: set[asyncio.Task[None]] = set()
        self._role_store = role_store
        self._policy = policy
        self._session_manager = session_manager
        self._generate_tool = generate_tool
        self._tool_registry = tool_registry
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        """Return a snapshot of in-flight automatic CG tasks."""

        return dict(self._tasks)

    def schedule(self, event: SceneObservationCommitted) -> None:
        """Schedule non-blocking CG generation from one scene observation."""

        if self._closed:
            return
        self._cancel_pending_task(event.session_key)
        if event.source == "passive":
            self._policy.advance_turn(event.session_key)
        # The consumer owns visual selection; closed/nonvisual observations never generate.
        if event.transition in {"closed", "none"} or not event.visual_description:
            return
        session = self._session_manager.get_or_create(event.session_key)
        role_id = str(event.role_id or session.metadata.get("role_id") or "").strip()
        role = self._role_store.get_role(role_id) if role_id else None
        if role is None or not bool(role.runtime_config.get("auto_scene_cg_enabled")):
            return
        if "generate_image" in event.tools_used:
            return
        required = event.transition in _REQUIRED_TRANSITIONS
        if not required and self._policy.cooldown_remaining(event.session_key) > 0:
            return
        task = create_runtime_task(
            self._run(event, role_id=role_id, bypass_cooldown=required),
            name=f"novelai_auto_cg:{event.session_key}",
        )
        self._tasks[event.session_key] = task
        self._all_tasks.add(task)
        task.add_done_callback(
            lambda completed, session_key=event.session_key: self._finish_task(
                session_key,
                completed,
            )
        )

    async def terminate(self) -> None:
        """Cancel and await all in-flight automatic CG tasks."""

        self._closed = True
        tasks = list(self._all_tasks)
        for task in tasks:
            _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run(
        self,
        event: SceneObservationCommitted,
        *,
        role_id: str,
        bypass_cooldown: bool,
    ) -> None:
        prepared = self._policy.guard(
            event.session_key,
            {
                "mode": "txt2img",
                "intent": "scene_cg",
                "scene_key": event.scene_key,
                "visual_key": event.visual_key,
                "role_id": role_id,
                "session_key": event.session_key,
            },
            bypass_cooldown=bypass_cooldown,
        )
        if not isinstance(prepared, dict):
            logger.info(
                "自动场景 CG 已跳过 session=%s reason=%s",
                event.session_key,
                getattr(prepared, "reason", "policy_denied"),
            )
            return
        prompt = await self._prompt_provider(
            self._light_provider,
            model=self._light_model,
            event=event,
        )
        prepared = self._policy.guard(
            event.session_key,
            {**prepared, **prompt},
            bypass_cooldown=bypass_cooldown,
        )
        if not isinstance(prepared, dict):
            return
        media = await self._generate_media_with_retry(
            prepared,
            session_key=event.session_key,
        )
        if not media:
            return

        push_tool = self._tool_registry.get_tool("message_push")
        if push_tool is None:
            raise RuntimeError("自动场景 CG 缺少 message_push 工具")
        image_path = media[0]
        push_result = await push_tool.execute(
            channel=event.channel,
            chat_id=event.chat_id,
            image=image_path,
            role_id=role_id,
            session_key=event.session_key,
        )
        if not isinstance(push_result, str) or "图片已发送" not in push_result:
            raise RuntimeError(f"自动场景 CG 补发失败: {push_result}")
        self._policy.record_success(event.session_key, prepared["visual_key"])

    async def _generate_media_with_retry(
        self,
        prepared: dict[str, Any],
        *,
        session_key: str,
    ) -> list[str]:
        for attempt in range(_MAX_GENERATION_RETRIES + 1):
            try:
                payload = _safe_json(await self._generate_tool.execute(**prepared))
                media = _media_paths(payload)
                if not media:
                    raise RuntimeError("自动场景 CG 生图结果缺少 output_paths")
                return media[:1]
            except Exception as error:
                if attempt < _MAX_GENERATION_RETRIES:
                    logger.warning(
                        "自动场景 CG 生图失败，准备重试 session=%s attempt=%d/%d: %s",
                        session_key,
                        attempt + 1,
                        _MAX_GENERATION_RETRIES,
                        error,
                    )
                    continue
                logger.error(
                    "自动场景 CG 生图失败，已重试 %d 次，放弃 session=%s: %s",
                    _MAX_GENERATION_RETRIES,
                    session_key,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )
        return []

    def _cancel_pending_task(self, session_key: str) -> None:
        task = self._tasks.pop(session_key, None)
        if task is not None and not task.done():
            task.cancel()

    def _finish_task(self, session_key: str, task: asyncio.Task[None]) -> None:
        self._all_tasks.discard(task)
        if self._tasks.get(session_key) is task:
            self._tasks.pop(session_key, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "自动场景 CG 后台任务失败 session=%s: %s",
                session_key,
                error,
                exc_info=(type(error), error, error.__traceback__),
            )


def _safe_json(text: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _media_paths(payload: dict[str, Any]) -> list[str]:
    raw_paths = payload.get("output_paths")
    if not isinstance(raw_paths, list):
        return []
    return [str(item).strip() for item in raw_paths if str(item).strip()]
