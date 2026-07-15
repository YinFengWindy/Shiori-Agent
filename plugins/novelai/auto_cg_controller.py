from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from agent.lifecycle.types import AfterTurnCtx, BeforeTurnCtx
from agent.tools.image_generate import GenerateImageTool
from agent.tools.registry import ToolRegistry
from core.integrations.novelai.models import NovelAISettings
from core.roles.store import RoleStore
from plugins.novelai.auto_cg import AutoCgPolicy
from plugins.novelai.scene_decision import (
    SceneCgDecision,
    SceneCgDecisionInput,
    decide_scene_cg,
)

logger = logging.getLogger(__name__)

_MAX_GENERATION_RETRIES = 1
_MAX_DECISION_RETRIES = 1


@dataclass(frozen=True)
class _SceneDecisionWork:
    decision_input: SceneCgDecisionInput
    auto_cg_enabled: bool


class AutoCgController:
    """Own asynchronous scene decisions, generation, and delayed delivery."""

    def __init__(
        self,
        *,
        settings: NovelAISettings,
        role_store: RoleStore,
        policy: AutoCgPolicy,
        light_provider: Any,
        light_model: str,
        session_manager: Any,
        generate_tool: GenerateImageTool,
        tool_registry: ToolRegistry,
        decision_provider: Callable[..., Awaitable[SceneCgDecision]] = decide_scene_cg,
        scene_transition_fn: Callable[[str, str, str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._role_store = role_store
        self._policy = policy
        self._light_provider = light_provider
        self._light_model = str(light_model or "").strip()
        self._session_manager = session_manager
        self._generate_tool = generate_tool
        self._tool_registry = tool_registry
        self._decision_provider = decision_provider
        self._scene_transition_fn = scene_transition_fn
        self._turn_inputs: dict[str, _SceneDecisionWork] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def capture_turn(self, ctx: BeforeTurnCtx) -> None:
        """Capture one eligible role turn and advance its cooldown counter."""

        self._cancel_pending_task(ctx.session_key)
        self._policy.advance_turn(ctx.session_key)
        decision_work = self._build_decision_input(ctx)
        if decision_work is None:
            self._turn_inputs.pop(ctx.session_key, None)
            return
        self._turn_inputs[ctx.session_key] = decision_work

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        """Return a snapshot of in-flight automatic CG tasks."""

        return dict(self._tasks)

    def schedule(self, ctx: AfterTurnCtx) -> None:
        """Schedule a non-blocking scene decision after the text turn completes."""

        decision_work = self._turn_inputs.pop(ctx.session_key, None)
        if (
            decision_work is None
            or not ctx.will_dispatch
            or not ctx.reply.strip()
            or ctx.session_key in self._tasks
        ):
            return
        auto_cg_allowed = (
            decision_work.auto_cg_enabled
            and "generate_image" not in ctx.tools_used
            and self._policy.cooldown_remaining(ctx.session_key) == 0
        )
        task = asyncio.create_task(
            self._run(
                ctx,
                decision_work.decision_input,
                auto_cg_allowed=auto_cg_allowed,
            ),
            name=f"novelai_auto_cg:{ctx.session_key}",
        )
        self._tasks[ctx.session_key] = task
        task.add_done_callback(
            lambda completed, session_key=ctx.session_key: self._finish_task(
                session_key,
                completed,
            )
        )

    async def terminate(self) -> None:
        """Cancel and await all in-flight automatic CG tasks."""

        tasks = list(self._tasks.values())
        for task in tasks:
            _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _build_decision_input(
        self,
        ctx: BeforeTurnCtx,
    ) -> _SceneDecisionWork | None:
        if (
            self._light_provider is None
            or not self._light_model
            or self._session_manager is None
        ):
            return None
        session = self._session_manager.get_or_create(ctx.session_key)
        role_id = str(session.metadata.get("role_id") or "").strip()
        if not role_id:
            return None
        role = self._role_store.get_role(role_id)
        if role is None:
            return None
        auto_cg_enabled = self._settings.enabled and bool(
            role.runtime_config.get("auto_scene_cg_enabled")
        )
        scene_followup_enabled = (
            self._scene_transition_fn is not None and role.proactive.enabled
        )
        if not auto_cg_enabled and not scene_followup_enabled:
            return None
        return _SceneDecisionWork(
            decision_input=SceneCgDecisionInput(
                role_name=role.name,
                role_prompt=role.system_prompt,
                user_message=ctx.content,
                recent_history=_compact_history(ctx.history_messages),
            ),
            auto_cg_enabled=auto_cg_enabled,
        )

    def _cancel_pending_task(self, session_key: str) -> None:
        task = self._tasks.pop(session_key, None)
        if task is not None and not task.done():
            task.cancel()

    async def _run(
        self,
        ctx: AfterTurnCtx,
        decision_input: SceneCgDecisionInput,
        *,
        auto_cg_allowed: bool = True,
    ) -> None:
        completed_input = SceneCgDecisionInput(
            role_name=decision_input.role_name,
            role_prompt=decision_input.role_prompt,
            user_message=decision_input.user_message,
            assistant_reply=ctx.reply,
            recent_history=decision_input.recent_history,
        )
        decision = await self._decide_with_retry(
            completed_input,
            session_key=ctx.session_key,
        )
        if self._scene_transition_fn is not None:
            self._scene_transition_fn(
                ctx.session_key,
                decision.scene_transition,
                decision.scene_key,
            )
        if not decision.should_generate or not auto_cg_allowed:
            return
        session = self._session_manager.get_or_create(ctx.session_key)
        role_id = str(session.metadata.get("role_id") or "").strip()
        prepared = self._policy.guard(
            ctx.session_key,
            {
                "prompt": decision.prompt,
                "negative_prompt": decision.negative_prompt,
                "mode": "txt2img",
                "size_preset": decision.size_preset,
                "intent": "scene_cg",
                "scene_key": decision.scene_key,
                "role_id": role_id,
                "session_key": ctx.session_key,
            },
        )
        if not isinstance(prepared, dict):
            logger.info(
                "自动场景 CG 已跳过 session=%s reason=%s",
                ctx.session_key,
                getattr(prepared, "reason", "policy_denied"),
            )
            return
        media = await self._generate_media_with_retry(
            prepared,
            session_key=ctx.session_key,
        )
        if not media:
            return

        push_tool = self._tool_registry.get_tool("message_push")
        if push_tool is None:
            raise RuntimeError("自动场景 CG 缺少 message_push 工具")
        image_path = media[0]
        push_result = await push_tool.execute(
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            image=image_path,
            role_id=role_id,
            session_key=ctx.session_key,
        )
        if not isinstance(push_result, str) or "图片已发送" not in push_result:
            raise RuntimeError(f"自动场景 CG 补发失败: {push_result}")
        self._policy.record_success(ctx.session_key, prepared["scene_key"])

    async def _decide_with_retry(
        self,
        decision_input: SceneCgDecisionInput,
        *,
        session_key: str,
    ) -> SceneCgDecision:
        for attempt in range(_MAX_DECISION_RETRIES + 1):
            try:
                return await self._decision_provider(
                    self._light_provider,
                    model=self._light_model,
                    decision_input=decision_input,
                )
            except Exception as error:
                if attempt < _MAX_DECISION_RETRIES:
                    logger.warning(
                        "自动场景 CG 判定失败，准备重试 session=%s attempt=%d/%d: %s",
                        session_key,
                        attempt + 1,
                        _MAX_DECISION_RETRIES,
                        error,
                    )
                    continue
                logger.error(
                    "自动场景 CG 判定失败，已重试 %d 次，放弃 session=%s: %s",
                    _MAX_DECISION_RETRIES,
                    session_key,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )
                raise
        raise RuntimeError("自动场景 CG 判定未完成")

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

    def _finish_task(
        self,
        session_key: str,
        task: asyncio.Task[None],
    ) -> None:
        if self._tasks.get(session_key) is task:
            _ = self._tasks.pop(session_key, None)
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


def _compact_history(items: tuple[Any, ...]) -> tuple[dict[str, str], ...]:
    history: list[dict[str, str]] = []
    for item in items[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            history.append({"role": role, "content": content[:1000]})
    return tuple(history)


def _media_paths(payload: dict[str, Any]) -> list[str]:
    raw_paths = payload.get("output_paths")
    if not isinstance(raw_paths, list):
        return []
    return [str(item).strip() for item in raw_paths if str(item).strip()]
