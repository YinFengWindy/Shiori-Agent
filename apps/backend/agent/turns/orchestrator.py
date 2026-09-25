from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from agent.turns.outbound import OutboundDispatch, OutboundPort
from agent.turns.result import TurnResult
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from conversation.service import LegacySessionDescriptor, network_thread_id
from core.roles.reply_state import (
    RoleReplyContext,
    role_mood_catalog,
    reply_state_metadata,
    validate_role_reply,
)
from session.manager.models import build_session_message

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from agent.looping.ports import SessionServices

logger = logging.getLogger("agent.turn_orchestrator")


@dataclass
class TurnOrchestratorDeps:
    session: SessionServices
    outbound: OutboundPort
    event_bus: EventBus | None = None


class TurnOrchestrator:
    def __init__(self, deps: TurnOrchestratorDeps) -> None:
        self._session = deps.session
        self._outbound = deps.outbound
        self._event_bus = deps.event_bus

    def capture_reply_context(self, session_key: str) -> RoleReplyContext:
        """Capture role output constraints and the successful-state stamp per tick."""
        session = self._session.session_manager.get_or_create(session_key)
        return RoleReplyContext(
            moods=role_mood_catalog(session.metadata.get("role_runtime_config", {})),
            previous_updated_at=str(
                session.metadata.get("current_mood_updated_at", "")
            ),
        )

    async def handle_proactive_turn(
        self,
        *,
        result: TurnResult,
        session_key: str,
        channel: str,
        chat_id: str,
    ) -> bool:
        # 1. proactive 先处理 skip：不发消息，只跑 skip 路径副作用。
        if result.decision == "skip":
            await self._run_side_effects(result)
            return False

        if result.outbound is None:
            raise ValueError("proactive reply result requires outbound")
        if result.role_reply is None or result.reply_context is None:
            raise ValueError(
                "proactive reply requires validated role state and generation stamp"
            )

        content = result.outbound.content
        media = list(result.outbound.media or [])
        reply = validate_role_reply(
            {
                "content": content,
                "mood": result.role_reply.mood,
                "thought": result.role_reply.thought,
            },
            result.reply_context.moods,
            allow_empty_content=bool(media),
        )
        if reply != result.role_reply:
            raise ValueError("proactive outbound differs from the validated role reply")
        session = self._session.session_manager.get_or_create(session_key)
        source_metadata = self._build_source_metadata(
            session=session,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
        )
        # The transport receives only user content; all pending state stays private.
        message = self._build_proactive_message(
            content=content,
            media=media,
            result=result,
            metadata=source_metadata,
        )
        message["metadata"] = {
            **message["metadata"],
            "mood": reply.mood,
            "thought": reply.thought,
        }
        await self._run_effects(result.side_effects)
        try:
            sent = await self._session.session_manager.append_messages(
                session,
                [message],
                pending_messages=True,
                expected_mood_updated_at=result.reply_context.previous_updated_at,
                metadata_updates=reply_state_metadata(
                    reply,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                ),
                before_commit=lambda: self._dispatch_outbound(
                    channel=channel,
                    chat_id=chat_id,
                    content=content,
                    media=media,
                    metadata={**source_metadata, "pending_commit": True},
                ),
            )
        except Exception:
            await self._run_effects(result.failure_side_effects)
            raise

        # 4. 根据是否真正发送成功，分别执行 success / failure side_effects。
        if sent:
            session = self._session.session_manager.get_or_create(session_key)
            if self._session.presence:
                role_id = str(
                    getattr(session, "metadata", {}).get("role_id") or ""
                ).strip()
                if role_id:
                    self._session.presence.record_proactive_sent_by_role(role_id)
                else:
                    self._session.presence.record_proactive_sent(session_key)
            if self._session.relationship_runtime is not None:
                self._session.relationship_runtime.handle_proactive_sent(session_key)
            await self._run_effects(result.success_side_effects)
            if self._event_bus is not None:
                await self._event_bus.fanout(
                    ProactiveMessageCommitted(
                        session_key=session_key,
                        channel=channel,
                        role_id=str(
                            getattr(session, "metadata", {}).get("role_id") or ""
                        ).strip(),
                        chat_id=chat_id,
                        assistant_response=content,
                        tools_used=("message_push",),
                    )
                )
        else:
            await self._run_effects(result.failure_side_effects)

        return sent

    async def _run_side_effects(self, result: TurnResult) -> None:
        await self._run_effects(result.side_effects)

    async def _run_effects(self, effects: list[Any]) -> None:
        for effect in effects:
            try:
                maybe = effect.run()
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception as e:
                logger.warning("turn side effect failed: %s", e)

    async def _dispatch_outbound(
        self,
        *,
        channel: str,
        chat_id: str,
        content: str,
        media: list[str],
        metadata: dict[str, Any],
    ) -> bool:
        return await self._outbound.dispatch(
            OutboundDispatch(
                channel=channel,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
                media=media,
            )
        )

    def _build_proactive_message(
        self,
        *,
        content: str,
        media: list[str],
        result: TurnResult,
        metadata: dict[str, str],
    ) -> dict[str, Any]:
        source_refs = []
        state_summary_tag = "none"
        if result.trace is not None and isinstance(result.trace.extra, dict):
            raw_refs = result.trace.extra.get("source_refs", [])
            if isinstance(raw_refs, list):
                source_refs = [ref for ref in raw_refs if isinstance(ref, dict)]
            state_summary_tag = str(result.trace.extra.get("state_summary_tag", "none"))
        return build_session_message(
            "assistant",
            content,
            media=media if media else None,
            proactive=True,
            tools_used=["message_push"],
            evidence_item_ids=[str(item_id) for item_id in result.evidence],
            source_refs=source_refs,
            state_summary_tag=state_summary_tag,
            metadata=metadata,
        )

    def _build_source_metadata(
        self,
        *,
        session: SessionLike,
        session_key: str,
        channel: str,
        chat_id: str,
    ) -> dict[str, str]:
        """Builds immutable source metadata for proactive role messages."""

        role_id = str(getattr(session, "metadata", {}).get("role_id") or "").strip()
        metadata = {
            "source": "proactive",
            "sender_id": "proactive",
            "chat_type": "desktop" if channel == "desktop" else "unknown",
            "context_channel": channel,
            "context_chat_id": chat_id,
            "transport_channel": channel,
            "transport_chat_id": chat_id,
        }
        if not role_id:
            return metadata
        conversation = getattr(self._session, "conversation_service", None)
        if conversation is not None:
            if channel == "desktop":
                thread_id = conversation.ensure_desktop_thread(role_id).id
            else:
                thread_id = conversation.ensure_thread_for_session(
                    LegacySessionDescriptor(
                        session_key=f"{channel}:{chat_id}",
                        role_id=role_id,
                        channel=channel,
                        chat_id=chat_id,
                    )
                ).id
        else:
            thread_id = network_thread_id(role_id, channel, chat_id)
        metadata.update(
            {
                "role_id": role_id,
                "thread_id": thread_id,
                "session_key_override": session_key,
            }
        )
        return metadata
