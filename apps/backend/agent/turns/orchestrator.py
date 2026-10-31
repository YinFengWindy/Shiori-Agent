from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager, nullcontext
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from agent.turns.outbound import OutboundDispatch, OutboundPort
from agent.account_delivery import AccountDelivery
from agent.turns.result import TurnResult
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from conversation.service import LegacySessionDescriptor, desktop_thread_id
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.accounts.routing import AccountRoute
from shiori_sdk.channels.chat_types import CHAT_TYPE_PRIVATE
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.timekit import utcnow
from core.roles.affection_access import current_affection
from core.roles.reply_policy import natural_chat_selected
from core.roles.services import RoleSessionService
from core.roles.reply_state import (
    RoleReplyContext,
    role_mood_catalog,
    reply_state_metadata,
    validate_role_reply,
)
from session.manager.helpers import role_session_key
from session.manager.models import build_session_message
from agent.account_delivery.service import ResolvedAccountTarget
from agent.turns.channel_sequence import channel_sequence_context
from agent.turns.reply_interruption import ReplyInterruption, reply_interruption_scope
from agent.turns.proactive_sequence import (
    ProactiveReplyPlan,
    current_proactive_reply,
    proactive_reply_scope,
    commit_proactive_sequence,
)
from core.common.runtime_scope import current_runtime_lease
from core.common.cancellation import finish_started
from core.roles.turn_gate import reacquire_role_gate
from shiori_sdk.messages import InboundMessage

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from agent.looping.ports import SessionServices
    from core.roles.store import RoleRecord

logger = logging.getLogger("agent.turn_orchestrator")


# (role_id, channel, chat_id) of an external proactive target -> the account
# channel and private target reaching it; raises LookupError for any other chat.
BoundChatTargetLookup = Callable[[str, str, str], tuple[str, AccountTarget]]


@dataclass
class TurnOrchestratorDeps:
    """Collaborators of ``TurnOrchestrator``.

    ``bound_chat_target`` resolves an external default proactive target (a
    private chat with the bound user) to the account that delivers it; it is
    required whenever a proactive turn can target anything but the desktop.
    """

    session: SessionServices
    outbound: OutboundPort
    event_bus: EventBus | None = None
    account_delivery: AccountDelivery | None = None
    bound_chat_target: BoundChatTargetLookup | None = None
    role_lookup: Callable[[str], RoleRecord | None] | None = None


class TurnOrchestrator:
    def __init__(self, deps: TurnOrchestratorDeps) -> None:
        self._session = deps.session
        self._outbound = deps.outbound
        self._event_bus = deps.event_bus
        self._account_delivery = deps.account_delivery
        self._bound_chat_target = deps.bound_chat_target
        self._role_lookup = deps.role_lookup

    def natural_chat_enabled(self, session_key: str) -> bool:
        """Read the role record at the start of each proactive tick.

        The session copy of ``role_runtime_config`` is not a switch. No lookup
        means there is no role record, so the switch is off.
        """
        if self._role_lookup is None:
            return False
        return natural_chat_selected(
            self._role_lookup(session_key.removeprefix("role:"))
        )

    async def _reply_origin(
        self,
        session_key: str,
        channel: str,
        chat_id: str,
        *,
        turn_id: str,
        account_target: dict | None = None,
    ) -> tuple[InboundMessage, ResolvedAccountTarget | None]:
        session = self._session.session_manager.get_or_create(session_key)
        role_id = str(session.metadata.get("role_id") or "")
        resolved = None
        if account_target is not None or channel != DESKTOP_CHANNEL:
            if self._account_delivery is None:
                raise RuntimeError("账号目标发送服务不可用")
            if account_target is not None:
                account_channel = str(account_target.get("account_channel") or "")
                target = AccountTarget.from_arguments(account_target)
            else:
                if self._bound_chat_target is None:
                    raise RuntimeError("外部主动推送目标需要绑定私聊的投递解析")
                account_channel, target = self._bound_chat_target(
                    role_id, channel, chat_id
                )
            resolved = await self._account_delivery.resolve_target(
                account_channel,
                role_id,
                target,
                known_private_route=(
                    AccountRoute(channel, chat_id) if account_target is None else None
                ),
            )
            channel, chat_id = resolved.route.channel, resolved.route.chat_id
        metadata = self._build_source_metadata(
            session=session,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            chat_type=resolved.route.chat_type if resolved is not None else None,
        )
        metadata["turn_id"] = turn_id
        if resolved is not None:
            metadata.update(
                account_id=resolved.access.account_id,
                chat_type=resolved.route.chat_type,
                message_thread_id=str(resolved.route.message_thread_id or ""),
            )
        return (
            InboundMessage(
                channel=channel,
                chat_id=chat_id,
                sender="proactive",
                content="",
                metadata=metadata,
            ),
            resolved,
        )

    @asynccontextmanager
    async def natural_reply_scope(
        self,
        session_key: str,
        channel: str,
        chat_id: str,
        *,
        turn_id: str,
        interruption: ReplyInterruption | None = None,
    ):
        """Own the generated plan from the selected target through final accounting."""
        if not self.natural_chat_enabled(session_key):
            if interruption is not None:
                interruption.invalidate()
            with reply_interruption_scope(interruption):
                yield
            return
        from agent.core.passive_turn.natural_reply import NaturalReplyProtocol

        lease = current_runtime_lease()
        binding = (
            lease.reply_sequences.bind(lease.core.loop.bus)
            if lease is not None
            else nullcontext()
        )
        with binding:
            context = channel_sequence_context()
            if context is None:
                raise RuntimeError("主动自然回复缺少运行时投递所有者")
            origin, resolved = await self._reply_origin(
                session_key, channel, chat_id, turn_id=turn_id
            )
            reply = interruption or ReplyInterruption()
            lookup = self._role_lookup
            if lookup is not None:
                reply.role_lookup = lambda: lookup(str(origin.metadata["role_id"]))
            with context.owner.background_reply(
                origin, reply, senders=None
            ) as registration:
                plan = ProactiveReplyPlan(
                    NaturalReplyProtocol(), registration, resolved
                )
                with proactive_reply_scope(plan), reply_interruption_scope(reply):
                    yield

    async def retarget_natural_reply(self, session_key: str, target: dict) -> None:
        """Bind a validated proactive draft's explicit target before another step."""
        plan = current_proactive_reply()
        if plan is None:
            return
        origin, resolved = await self._reply_origin(
            session_key,
            plan.origin.channel,
            plan.origin.chat_id,
            turn_id=str(plan.origin.metadata["turn_id"]),
            account_target=target,
        )
        assert resolved is not None
        self._retarget_plan(
            plan,
            origin,
            resolved,
            senders=frozenset(resolved.target.mention_ids) or None,
        )

    async def retarget_natural_transport(
        self, session_key: str, channel: str, chat_id: str
    ) -> None:
        """Honor Drift's late target selector and authorize its exact new address."""
        plan = current_proactive_reply()
        if plan is None or (plan.origin.channel, plan.origin.chat_id) == (
            channel,
            chat_id,
        ):
            return
        origin, resolved = await self._reply_origin(
            session_key,
            channel,
            chat_id,
            turn_id=str(plan.origin.metadata["turn_id"]),
        )
        self._retarget_plan(plan, origin, resolved, senders=None)

    @staticmethod
    def _retarget_plan(
        plan: ProactiveReplyPlan,
        origin: InboundMessage,
        resolved: ResolvedAccountTarget | None,
        *,
        senders: frozenset[str] | None,
    ) -> None:
        """Replace an authorized target and fence together on the registered plan."""
        plan.account_target = resolved
        context = channel_sequence_context()
        assert context is not None
        context.owner.retarget_background(plan.registration, origin, senders=senders)

    def capture_reply_context(self, session_key: str) -> RoleReplyContext:
        """Capture role output constraints and the successful-state stamp per tick."""
        session = self._session.session_manager.get_or_create(session_key)
        if self._role_lookup is not None:
            role = self._role_lookup(str(session.metadata.get("role_id") or ""))
            if role is None:
                raise ValueError("主动回复的角色已删除")
            session = RoleSessionService(self._session.session_manager).open_by_role(
                role
            )
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
        source: str = "",
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
        plan = current_proactive_reply()
        if plan is not None:
            return await self._handle_natural_reply(
                result=result,
                session=session,
                template=message,
                plan=plan,
                source=source,
                state_kwargs={
                    "expected_mood_updated_at": result.reply_context.previous_updated_at,
                    "metadata_updates": reply_state_metadata(
                        reply,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    ),
                },
            )
        account_target = (
            result.trace.extra.get("account_target")
            if result.trace is not None and isinstance(result.trace.extra, dict)
            else None
        )
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
                before_commit=lambda: self._deliver_before_commit(
                    message,
                    channel=channel,
                    chat_id=chat_id,
                    content=content,
                    media=media,
                    metadata={**source_metadata, "pending_commit": True},
                    account_target=account_target,
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
                self._session.presence.record_initiated_sent(
                    role_session_key(role_id) if role_id else session_key,
                    utcnow(),
                )
            affection = current_affection()
            if affection is not None:
                affection.handle_initiated_sent(session_key)
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
                        thread_id=source_metadata.get("thread_id", ""),
                        message_id=str(message["id"]),
                        source=source,
                    )
                )
        else:
            await self._run_effects(result.failure_side_effects)

        return sent

    async def _handle_natural_reply(
        self,
        *,
        result: TurnResult,
        session,
        template: dict[str, Any],
        plan: ProactiveReplyPlan,
        source: str,
        state_kwargs: dict[str, Any],
    ) -> bool:
        reply = plan.protocol.reply
        if reply is None:
            raise ValueError("主动自然回复尚未通过消息列表校验")
        # Proactive drafts have no content decorators. Consume the validated
        # messages directly, keeping opaque passive-hook boundaries out of
        # proactive logs, duplicate keys and subsequent tool requests.
        if template["content"] != reply.sequence.content:
            raise ValueError("主动草稿与已校验消息列表不一致")
        sequence = reply.sequence
        delivered: list[dict[str, Any]] = []
        await self.commit_proactive_tool_facts(session.key)
        await self._run_effects(result.side_effects)
        try:
            await commit_proactive_sequence(
                plan=plan,
                sequence=sequence,
                template=template,
                manager=self._session.session_manager,
                session=session,
                outbound=self._outbound,
                account_delivery=self._account_delivery,
                event_bus=self._event_bus,
                state_kwargs=state_kwargs,
                delivered=delivered,
            )
            return True
        finally:

            async def finalize() -> None:
                await reacquire_role_gate()
                await self._run_effects(
                    result.success_side_effects
                    if len(delivered) == len(sequence.messages)
                    else result.failure_side_effects
                )
                if not delivered:
                    return
                role_id = str(plan.origin.metadata.get("role_id") or "")
                if self._session.presence:
                    self._session.presence.record_initiated_sent(
                        role_session_key(role_id), utcnow()
                    )
                affection = current_affection()
                if affection is not None:
                    affection.handle_initiated_sent(session.key)
                if self._event_bus is not None:
                    await self._event_bus.fanout(
                        ProactiveMessageCommitted(
                            session_key=session.key,
                            role_id=role_id,
                            channel=plan.origin.channel,
                            chat_id=plan.origin.chat_id,
                            thread_id=str(plan.origin.metadata.get("thread_id") or ""),
                            assistant_response="\n\n".join(
                                str(m["content"]) for m in delivered
                            ),
                            tools_used=("message_push",),
                            message_id=str(delivered[-1]["id"]),
                            source=source,
                        )
                    )

            await finish_started(finalize())

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

    async def _deliver_before_commit(
        self,
        message: dict[str, Any],
        *,
        channel: str,
        chat_id: str,
        content: str,
        media: list[str],
        metadata: dict[str, Any],
        account_target: object = None,
    ) -> bool:
        """Sends the pending message and stamps its delivery facts before commit.

        The draft has no committed id yet, so instead of marking it afterwards
        the delivery_status / external_message_id fields ride on the draft and
        are written by the same insert that commits it (the session store
        persists both as message columns). Only a receipt for a message the
        platform actually accepted is stamped ``sent``. A refused or failed
        send commits nothing.

        An explicit ``account_target`` and every external default target (a
        private chat with the bound user, resolved by ``bound_chat_target``)
        go through the role's account; only the desktop is dispatched through
        the outbound port, and desktop messages never carry a delivery status.
        """
        role_id = str(metadata.get("role_id") or "")
        if isinstance(account_target, dict):
            account_channel = str(account_target.get("account_channel") or "")
            target = AccountTarget.from_arguments(account_target)
        elif channel != DESKTOP_CHANNEL:
            if self._bound_chat_target is None:
                raise RuntimeError("外部主动推送目标需要绑定私聊的投递解析")
            account_channel, target = self._bound_chat_target(role_id, channel, chat_id)
        else:
            receipt = await self._outbound.dispatch(
                OutboundDispatch(
                    channel=channel,
                    chat_id=chat_id,
                    content=content,
                    metadata=metadata,
                    media=media,
                )
            )
            return receipt is not None
        if self._account_delivery is None:
            raise RuntimeError("账号目标发送服务不可用")
        # The role's account on the named channel plugin sends it.
        receipt = await self._account_delivery.send(
            account_channel,
            role_id,
            target,
            content,
            source="proactive",
            media=media,
        )
        message["metadata"].update(receipt.message_metadata())
        message["delivery_status"] = "sent"
        message["external_message_id"] = receipt.platform_message_id
        return True

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
        chat_type: str | None = None,
    ) -> dict[str, str]:
        """Builds immutable source metadata for proactive role messages."""

        role_id = str(getattr(session, "metadata", {}).get("role_id") or "").strip()
        metadata = {
            "source": "proactive",
            "sender_id": "proactive",
            # Every external default target is a private chat with the bound
            # user (``bound_chat_target``).
            "chat_type": chat_type
            or ("desktop" if channel == "desktop" else CHAT_TYPE_PRIVATE),
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
                        metadata=metadata,
                    )
                ).id
        else:
            thread_id = (
                desktop_thread_id(role_id)
                if channel == DESKTOP_CHANNEL
                else network_thread_id(role_id, channel, chat_id)
            )
        metadata.update(
            {
                "role_id": role_id,
                "thread_id": thread_id,
                "session_key_override": session_key,
            }
        )
        return metadata

    async def commit_proactive_tool_facts(self, session_key: str) -> None:
        """Retain completed work once even when an unseen proactive plan is invalidated."""
        plan = current_proactive_reply()
        if plan is None or len(plan.tool_chain) == plan.committed_tool_count:
            return
        # Role deletion owns its storage; never recreate it during cleanup.
        if (
            self._role_lookup is not None
            and self._role_lookup(str(plan.origin.metadata["role_id"])) is None
        ):
            return
        manager = self._session.session_manager
        session = manager.get_or_create(session_key)
        message = build_session_message(
            "assistant",
            "",
            metadata={**plan.origin.metadata, "proactive_tool_facts": True},
            proactive=True,
            tool_chain=plan.tool_chain[plan.committed_tool_count :],
        )

        async def commit() -> None:
            await manager.append_messages(session, [message], pending_messages=True)
            plan.committed_tool_count = len(plan.tool_chain)

        await finish_started(commit())
