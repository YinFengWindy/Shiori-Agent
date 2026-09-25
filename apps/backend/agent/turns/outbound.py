from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from bus.events import OutboundMessage
from agent.tools.message_push import PENDING_TURN_DELIVERY

_INTERNAL_CITATION_RE = re.compile(r"\s*§cited:\[[^\]]*\]§\s*")


def sanitize_user_visible_content(content: str) -> str:
    """Consumes internal memory citation markers before transport delivery."""

    return _INTERNAL_CITATION_RE.sub(" ", str(content or "")).strip()


@dataclass
class OutboundDispatch:
    channel: str
    chat_id: str
    content: str
    thinking: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    media: list[str] = field(default_factory=list)
    # Carries the already-committed session message id (if any) through to the
    # published OutboundMessage, so delivery bookkeeping can target that exact
    # row instead of guessing the thread's latest assistant message.
    committed_message_id: str | None = None


class OutboundDispatchError(RuntimeError):
    """Indicates an unexpected transport or channel configuration failure."""

    def __init__(self, *, channel: str, chat_id: str, detail: object) -> None:
        self.channel = channel
        self.chat_id = chat_id
        self.detail = str(detail)
        super().__init__(
            f"outbound dispatch failed for {channel}:{chat_id}: {self.detail}"
        )


@dataclass(frozen=True)
class DeliveryReceipt:
    """Proof that a transport accepted an outbound payload.

    ``external_message_id`` is the platform id of the first message the
    transport sent, or empty when the transport cannot report one.
    """

    external_message_id: str = ""


class OutboundPort(Protocol):
    async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
        """Sends the payload; returns a receipt, or None when delivery was refused."""
        ...


class BusOutboundPort:
    def __init__(self, bus: Any) -> None:
        self._bus = bus

    async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
        """Queues the payload on the bus; the channel records delivery itself.

        The receipt only proves the hand-off to the bus, never the platform id:
        each channel's ``_on_response`` marks the committed message after it
        actually sends.
        """
        content = sanitize_user_visible_content(outbound.content)
        maybe = self._bus.publish_outbound(
            OutboundMessage(
                channel=outbound.channel,
                chat_id=outbound.chat_id,
                content=content,
                thinking=outbound.thinking,
                metadata=dict(outbound.metadata or {}),
                media=list(outbound.media or []),
                committed_message_id=outbound.committed_message_id,
            )
        )
        if inspect.isawaitable(maybe):
            await maybe
        return DeliveryReceipt()


class PushToolOutboundPort:
    def __init__(
        self,
        push_tool: Any,
        *,
        execution_context: dict[str, str] | None = None,
    ) -> None:
        self._push = push_tool
        self._execution_context = dict(execution_context or {})

    async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
        """Sends every payload part through the push tool, all or nothing.

        Returns a receipt carrying the first platform message id any sender
        reported; None when the target is empty or the role may not use it.
        """
        message = sanitize_user_visible_content(outbound.content)
        channel = str(outbound.channel or "").strip()
        chat_id = str(outbound.chat_id or "").strip()
        media = [str(item).strip() for item in outbound.media if str(item).strip()]
        if (not message and not media) or not channel or not chat_id:
            return None
        external_ids: list[str] = []
        execution_context = {
            **self._execution_context,
            "session_key": str(
                outbound.metadata.get("session_key_override") or ""
            ).strip(),
            "push_message_already_persisted": (
                "false" if outbound.metadata.get("pending_commit") else "true"
            ),
            **(
                {"_pending_turn_delivery": PENDING_TURN_DELIVERY}
                if outbound.metadata.get("pending_commit")
                else {}
            ),
        }
        try:
            if message or media:
                outcome = await self._push.push(
                    channel=channel,
                    chat_id=chat_id,
                    message=message,
                    image=media[0] if media else None,
                    **execution_context,
                )
                self._validate_delivery_result(
                    outcome.text, channel=channel, chat_id=chat_id
                )
                external_ids.extend(outcome.external_message_ids)
            for image in media[1:]:
                outcome = await self._push.push(
                    channel=channel,
                    chat_id=chat_id,
                    image=image,
                    **execution_context,
                )
                self._validate_delivery_result(
                    outcome.text, channel=channel, chat_id=chat_id
                )
                external_ids.extend(outcome.external_message_ids)
        except PermissionError:
            return None
        except OutboundDispatchError:
            raise
        except Exception as exc:
            raise OutboundDispatchError(
                channel=channel,
                chat_id=chat_id,
                detail=exc,
            ) from exc

        # One session message may span several platform messages (text, then
        # images) but has a single external_message_id column: keep the first.
        return DeliveryReceipt(
            external_message_id=external_ids[0] if external_ids else ""
        )

    @staticmethod
    def _validate_delivery_result(
        result: object, *, channel: str, chat_id: str
    ) -> None:
        """Every requested payload must succeed before a delivery can be committed."""
        result_text = str(result)
        if (
            "已发送" not in result_text
            or "不支持" in result_text
            or "发送失败" in result_text
        ):
            raise OutboundDispatchError(
                channel=channel,
                chat_id=chat_id,
                detail=result_text,
            )
