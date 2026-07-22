from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from agent.lifecycle.types import AfterTurnCtx, BeforeTurnCtx
from agent.plugins.context import PluginKVStore
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ProactiveMessageCommitted,
    SceneObservationCommitted,
    SceneTurnSource,
)
from core.roles.store import RoleStore
from plugins.scene_awareness.decision import (
    SceneDecision,
    SceneDecisionInput,
    decide_scene,
)

logger = logging.getLogger(__name__)

_MAX_DECISION_RETRIES = 1
_STATE_KEY = "scene_awareness_sessions"


@dataclass(frozen=True)
class _PendingTurn:
    decision_input: SceneDecisionInput
    source: SceneTurnSource
    session_key: str
    channel: str
    chat_id: str
    role_id: str
    tools_used: tuple[str, ...] = ()


class SceneAwarenessController:
    """Observes completed role turns and publishes durable scene decisions."""

    def __init__(
        self,
        *,
        role_store: RoleStore,
        session_manager: Any,
        event_bus: EventBus,
        kv_store: PluginKVStore,
        light_provider: Any,
        light_model: str,
        decision_provider: Any = decide_scene,
    ) -> None:
        self._role_store = role_store
        self._session_manager = session_manager
        self._event_bus = event_bus
        self._kv_store = kv_store
        self._light_provider = light_provider
        self._light_model = str(light_model or "").strip()
        self._decision_provider = decision_provider
        self._pending_turns: dict[str, _PendingTurn] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        """Return a snapshot of in-flight scene observation tasks."""

        return dict(self._tasks)

    def capture_passive_turn(self, ctx: BeforeTurnCtx) -> None:
        """Capture the user-side context needed after passive reasoning completes."""

        self._cancel_pending_task(ctx.session_key)
        pending = self._build_pending_turn(
            session_key=ctx.session_key,
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            role_id="",
            source="passive",
            user_message=ctx.content,
            history_messages=ctx.history_messages,
        )
        if pending is None:
            self._pending_turns.pop(ctx.session_key, None)
            return
        self._pending_turns[ctx.session_key] = pending

    def schedule_passive_turn(self, ctx: AfterTurnCtx) -> None:
        """Schedule scene observation for one completed passive role turn."""

        pending = self._pending_turns.pop(ctx.session_key, None)
        if pending is None or not ctx.will_dispatch or not ctx.reply.strip():
            return
        self._schedule(
            _PendingTurn(
                decision_input=pending.decision_input,
                source=pending.source,
                session_key=pending.session_key,
                channel=ctx.channel,
                chat_id=ctx.chat_id,
                role_id=pending.role_id,
                tools_used=tuple(ctx.tools_used),
            ),
            assistant_reply=ctx.reply,
        )

    def schedule_proactive_turn(self, event: ProactiveMessageCommitted) -> None:
        """Schedule scene observation for one committed proactive text message."""

        if not event.assistant_response.strip():
            return
        self._cancel_pending_task(event.session_key)
        pending = self._build_pending_turn(
            session_key=event.session_key,
            channel=event.channel,
            chat_id=event.chat_id,
            role_id=event.role_id,
            source="proactive",
            user_message="",
            history_messages=self._session_history(event.session_key),
            tools_used=event.tools_used,
        )
        if pending is None:
            return
        self._schedule(pending, assistant_reply=event.assistant_response)

    async def terminate(self) -> None:
        """Cancel and await all in-flight scene observation tasks."""

        tasks = list(self._tasks.values())
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
        history_messages: tuple[Any, ...],
        tools_used: tuple[str, ...] = (),
    ) -> _PendingTurn | None:
        if (
            self._light_provider is None
            or not self._light_model
            or self._session_manager is None
        ):
            return None
        session = self._session_manager.get_or_create(session_key)
        clean_role_id = str(role_id or session.metadata.get("role_id") or "").strip()
        if not clean_role_id:
            return None
        role = self._role_store.get_role(clean_role_id)
        if role is None:
            return None
        if not (
            role.proactive.enabled
            or bool(role.runtime_config.get("auto_scene_cg_enabled"))
        ):
            return None
        return _PendingTurn(
            decision_input=SceneDecisionInput(
                role_name=role.name,
                role_prompt=role.system_prompt,
                user_message=user_message,
                current_scene_key=self._current_scene_key(session_key),
                recent_history=_compact_history(history_messages),
            ),
            source=source,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            role_id=clean_role_id,
            tools_used=tuple(tools_used),
        )

    def _schedule(self, pending: _PendingTurn, *, assistant_reply: str) -> None:
        task = asyncio.create_task(
            self._run(pending, assistant_reply=assistant_reply),
            name=f"scene_awareness:{pending.session_key}",
        )
        self._tasks[pending.session_key] = task
        task.add_done_callback(
            lambda completed, session_key=pending.session_key: self._finish_task(
                session_key,
                completed,
            )
        )

    async def _run(self, pending: _PendingTurn, *, assistant_reply: str) -> None:
        source_input = pending.decision_input
        decision = await self._decide_with_retry(
            SceneDecisionInput(
                role_name=source_input.role_name,
                role_prompt=source_input.role_prompt,
                user_message=source_input.user_message,
                assistant_reply=assistant_reply,
                current_scene_key=source_input.current_scene_key,
                recent_history=source_input.recent_history,
            ),
            session_key=pending.session_key,
        )
        self._apply_scene_state(pending.session_key, decision)
        await self._event_bus.fanout(
            SceneObservationCommitted(
                session_key=pending.session_key,
                channel=pending.channel,
                chat_id=pending.chat_id,
                role_id=pending.role_id,
                source=pending.source,
                transition=decision.transition,
                scene_key=decision.scene_key,
                should_generate=decision.should_generate,
                prompt=decision.prompt,
                negative_prompt=decision.negative_prompt,
                size_preset=decision.size_preset,
                tools_used=pending.tools_used,
            )
        )

    async def _decide_with_retry(
        self,
        decision_input: SceneDecisionInput,
        *,
        session_key: str,
    ) -> SceneDecision:
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
                        "场景观察判定失败，准备重试 session=%s attempt=%d/%d: %s",
                        session_key,
                        attempt + 1,
                        _MAX_DECISION_RETRIES,
                        error,
                    )
                    continue
                logger.error(
                    "场景观察判定失败，已重试 %d 次，放弃 session=%s: %s",
                    _MAX_DECISION_RETRIES,
                    session_key,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )
                raise
        raise RuntimeError("场景观察判定未完成")

    def _current_scene_key(self, session_key: str) -> str:
        sessions = self._read_sessions()
        state = sessions.get(session_key)
        if not isinstance(state, dict):
            return ""
        return str(state.get("scene_key") or "").strip()

    def _apply_scene_state(self, session_key: str, decision: SceneDecision) -> None:
        sessions = self._read_sessions()
        if decision.transition == "closed":
            sessions.pop(session_key, None)
        elif decision.scene_key:
            sessions[session_key] = {"scene_key": decision.scene_key}
        self._kv_store.set(_STATE_KEY, sessions)

    def _read_sessions(self) -> dict[str, Any]:
        raw = self._kv_store.get(_STATE_KEY, {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _session_history(self, session_key: str) -> tuple[Any, ...]:
        session = self._session_manager.get_or_create(session_key)
        messages = getattr(session, "messages", ())
        return tuple(messages) if isinstance(messages, (list, tuple)) else ()

    def _cancel_pending_task(self, session_key: str) -> None:
        task = self._tasks.pop(session_key, None)
        if task is not None and not task.done():
            task.cancel()

    def _finish_task(self, session_key: str, task: asyncio.Task[None]) -> None:
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
