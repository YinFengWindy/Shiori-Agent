"""Observes completed role turns and publishes durable scene decisions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, replace
from typing import Any

from shiori_sdk.core.conversation import ConversationMessage, TurnFinished, TurnStarting
from shiori_sdk.core.scene import SceneHistoryMessage, SceneHost
from shiori_sdk.role_events import (
    ProactiveMessageCommitted,
    SceneObservationCommitted,
    SceneTurnSource,
)

from .contracts import SceneDecision, SceneDecisionInput, SceneDecisionProtocolError
from .decision import decide_scene
from .state import SceneStateStore

logger = logging.getLogger(__name__)

# 场景观察参考的最近消息条数。
_RECENT_HISTORY_LIMIT = 6

type Spawn = Callable[[Coroutine[Any, Any, None], str], asyncio.Task[None]]
type Publish = Callable[[SceneObservationCommitted], Awaitable[None]]


@dataclass(frozen=True)
class _PendingTurn:
    decision_input: SceneDecisionInput
    source: SceneTurnSource
    session_key: str
    channel: str
    chat_id: str
    role_id: str
    tools_used: tuple[str, ...] = ()
    revision: int = 0


class SceneAwarenessController:
    """Observes completed role turns and publishes durable scene decisions."""

    def __init__(
        self,
        *,
        host: SceneHost,
        state: SceneStateStore,
        light_provider: Any,
        light_model: str,
        spawn: Spawn,
        publish: Publish,
        decision_provider: Any = decide_scene,
        needs_observation: Callable[[str], bool] = lambda _role_id: False,
    ) -> None:
        self._needs_observation = needs_observation
        self._closed = False
        self._all_tasks: set[asyncio.Task[None]] = set()
        self._host = host
        self.state = state
        self._light_provider = light_provider
        self._light_model = str(light_model or "").strip()
        self._decision_provider = decision_provider
        self._spawn = spawn
        self._publish = publish
        self._pending_turns: dict[str, _PendingTurn] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        """Return a snapshot of in-flight scene observation tasks."""
        return dict(self._tasks)

    def capture_passive_turn(self, ctx: TurnStarting) -> None:
        """Capture the user-side context needed after passive reasoning completes.

        外部上下文的回合不观察：场景状态按角色共享，群聊与陌生私聊会污染用户的
        场景。同时丢掉可能残留的待观察回合，免得它配上外部回合的回复被调度。
        """
        if ctx.context_scope == "external":
            self._pending_turns.pop(ctx.session_key, None)
            return
        self._cancel_pending_task(ctx.session_key)
        pending = self._build_pending_turn(
            session_key=ctx.session_key,
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            role_id="",
            source="passive",
            user_message=ctx.content,
            history_messages=ctx.history,
        )
        if pending is None:
            self._pending_turns.pop(ctx.session_key, None)
            return
        self._pending_turns[ctx.session_key] = pending

    def schedule_passive_turn(self, ctx: TurnFinished) -> None:
        """Schedule scene observation for one completed passive role turn."""
        pending = self._pending_turns.pop(ctx.session_key, None)
        if pending is None or not ctx.reply.strip():
            return
        self._schedule(
            replace(
                pending,
                channel=ctx.channel,
                chat_id=ctx.chat_id,
                tools_used=tuple(ctx.tools_used),
            ),
            assistant_reply=ctx.reply,
        )

    def schedule_proactive_turn(self, event: ProactiveMessageCommitted) -> None:
        """Schedule scene observation for one committed proactive text message.

        按事件自带的 ``thread_id`` 判定上下文，外部上下文不观察。
        """
        if not event.assistant_response.strip() or not self._can_observe():
            return
        history = self._host.proactive_history(
            session_key=event.session_key,
            role_id=event.role_id,
            thread_id=event.thread_id,
            limit=_RECENT_HISTORY_LIMIT,
        )
        if history is None:
            return
        self._cancel_pending_task(event.session_key)
        pending = self._build_pending_turn(
            session_key=event.session_key,
            channel=event.channel,
            chat_id=event.chat_id,
            role_id=event.role_id,
            source="proactive",
            user_message="",
            history_messages=history,
            tools_used=event.tools_used,
        )
        if pending is None:
            return
        self._schedule(pending, assistant_reply=event.assistant_response)

    async def terminate(self) -> None:
        """Cancel and await all in-flight scene observation tasks."""
        self._closed = True
        tasks = list(self._all_tasks)
        for task in tasks:
            _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._pending_turns.clear()

    def _build_pending_turn(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        role_id: str,
        source: SceneTurnSource,
        user_message: str,
        history_messages: Sequence[SceneHistoryMessage | ConversationMessage],
        tools_used: tuple[str, ...] = (),
    ) -> _PendingTurn | None:
        if not self._can_observe():
            return None
        subject = self._host.subject(session_key, role_id)
        if subject is None or not self._needs_observation(subject.id):
            return None
        current = self.state.current(session_key)
        return _PendingTurn(
            decision_input=SceneDecisionInput(
                role_name=subject.name,
                role_prompt=subject.system_prompt,
                user_message=user_message,
                current_scene_key=current["scene_key"],
                current_visual_key=current["visual_key"],
                recent_history=_compact_history(history_messages),
            ),
            source=source,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            role_id=subject.id,
            tools_used=tuple(tools_used),
            revision=self.state.reserve(session_key),
        )

    def _can_observe(self) -> bool:
        """控制器未关闭且观察所需的轻量模型已配置。"""
        return (
            not self._closed
            and self._light_provider is not None
            and bool(self._light_model)
        )

    def _schedule(self, pending: _PendingTurn, *, assistant_reply: str) -> None:
        if self._closed:
            return
        task = self._spawn(
            self._run(pending, assistant_reply=assistant_reply),
            f"scene_awareness:{pending.session_key}",
        )
        self._tasks[pending.session_key] = task
        self._all_tasks.add(task)
        task.add_done_callback(
            lambda completed, session_key=pending.session_key: self._finish_task(
                session_key,
                completed,
            )
        )

    async def _run(self, pending: _PendingTurn, *, assistant_reply: str) -> None:
        source_input = pending.decision_input
        decision = await self._decide(
            replace(source_input, assistant_reply=assistant_reply),
            session_key=pending.session_key,
        )
        if not self.state.is_current(pending.session_key, pending.revision):
            return
        self.state.apply(pending.session_key, decision)
        await self._publish(
            SceneObservationCommitted(
                session_key=pending.session_key,
                channel=pending.channel,
                chat_id=pending.chat_id,
                role_id=pending.role_id,
                source=pending.source,
                transition=decision.transition,
                scene_key=decision.scene_key,
                visual_key=decision.visual_key,
                visual_description=decision.visual_description,
                role_name=source_input.role_name,
                role_description=source_input.role_prompt,
                user_message=source_input.user_message,
                assistant_reply=assistant_reply,
                tools_used=pending.tools_used,
            )
        )

    async def _decide(
        self,
        decision_input: SceneDecisionInput,
        *,
        session_key: str,
    ) -> SceneDecision:
        try:
            return await self._decision_provider(
                self._light_provider,
                model=self._light_model,
                decision_input=decision_input,
            )
        except SceneDecisionProtocolError as error:
            logger.error(
                "场景观察协议失败 session=%s reason=%s tool_calls=%d tools=%s keys=%s content_chars=%d",
                session_key,
                error,
                error.tool_call_count,
                error.tool_names,
                error.argument_keys,
                error.content_length,
            )
            raise

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
                "场景观察后台任务失败 session=%s: %s",
                session_key,
                error,
                exc_info=(type(error), error, error.__traceback__),
            )


def _compact_history(
    items: Sequence[SceneHistoryMessage | ConversationMessage],
) -> tuple[dict[str, str], ...]:
    """取最近 ``_RECENT_HISTORY_LIMIT`` 条消息转成 role/content 对。

    role 或 content 为空的消息直接丢弃，不向前补足；content 截断到 1000 字符。
    """
    history: list[dict[str, str]] = []
    for item in items[-_RECENT_HISTORY_LIMIT:]:
        role = item.role.strip()
        content = item.content.strip()
        if role and content:
            history.append({"role": role, "content": content[:1000]})
    return tuple(history)
