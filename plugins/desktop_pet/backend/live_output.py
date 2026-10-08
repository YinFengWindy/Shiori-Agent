"""Backend side of the pet's live-reply output contract.

The live engine (#724) cannot call the pet's TTS from Python, so output runs
in the pet background. This module owns the wire contract, mirrored by
``background/live/contract.ts``:

- event ``live.reply.show`` ``{source: "live", role_id, reply_id, run_id, text}``
- event ``live.cancel`` ``{run_id?}``; without ``run_id`` every live reply stops
- RPC ``live.reply.outcome`` ``{reply_id, run_id, bubble, speech}`` where each
  channel is ``{status: "succeeded" | "failed" | "cancelled" | "skipped", error?}``;
  ``skipped`` (speech only) means pet speech was off at the reply's turn.

Outcome guarantee: every emitted ``live.reply.show`` is answered by exactly one
outcome while the pet background is alive — ``failed`` for a malformed reply
or a role the pet does not show, ``cancelled`` for a cancelled run, a user
stop, a role switch or plugin disable. A cancelled run stays cancelled for the
current pet role, so the engine never needs to suppress late replies itself.
The one gap is transport: ``show`` returning False means no background got it.
"""

import logging

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from shiori_sdk.rpc import Concurrency, RpcCapability

LIVE_REPLY_SHOW = "live.reply.show"
LIVE_CANCEL = "live.cancel"
LIVE_REPLY_OUTCOME = "live.reply.outcome"

OutputStatus = Literal["succeeded", "failed", "cancelled", "skipped"]
_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled", "skipped"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutputResult:
    """How one output channel (bubble or speech) ended for one reply."""

    status: OutputStatus
    error: str = ""


@dataclass(frozen=True)
class LiveReplyOutcome:
    """The pet background's report for one shown live reply."""

    reply_id: str
    run_id: str
    bubble: OutputResult
    speech: OutputResult


type OutcomeListener = Callable[[LiveReplyOutcome], Awaitable[None]]


class LiveReplyOutput:
    """Sends live replies to the pet background and forwards their outcomes.

    Constructing it registers the outcome RPC, so exactly one instance exists
    per plugin setup; the live engine subscribes to learn each reply's bubble
    and speech result by reply id.

    The RPC runs on the default MUTATION lane: delivering an outcome changes
    subscriber state (the engine's in-flight bookkeeping), so it must not race
    other plugin writes the way READ_ONLY handlers may. It is admission-exempt
    because an outcome rejected during a settings reload would break the
    one-outcome-per-reply guarantee, and the handler is bounded.
    """

    def __init__(self, rpc: RpcCapability) -> None:
        self._rpc = rpc
        self._listeners: list[OutcomeListener] = []
        rpc.register(
            LIVE_REPLY_OUTCOME,
            self._receive,
            concurrency=Concurrency.MUTATION,
            admission_exempt=True,
        )

    async def show(
        self, *, role_id: str, reply_id: str, run_id: str, text: str
    ) -> bool:
        """Asks the pet to show and speak one reply; returns transport delivery."""
        return await self._rpc.emit(
            LIVE_REPLY_SHOW,
            {
                "source": "live",
                "role_id": role_id,
                "reply_id": reply_id,
                "run_id": run_id,
                "text": text,
            },
        )

    async def cancel(self, run_id: str | None = None) -> bool:
        """Cancels live output only (of one run when given); chat output is untouched."""
        return await self._rpc.emit(
            LIVE_CANCEL, {} if run_id is None else {"run_id": run_id}
        )

    def subscribe(self, listener: OutcomeListener) -> Callable[[], None]:
        """Adds an outcome listener; the returned callable removes it, once."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def _receive(self, payload: dict[str, Any]) -> dict[str, Any]:
        outcome = LiveReplyOutcome(
            reply_id=_require_text(payload, "reply_id"),
            run_id=_require_text(payload, "run_id"),
            bubble=_read_result(payload, "bubble"),
            speech=_read_result(payload, "speech"),
        )
        for listener in list(self._listeners):
            await listener(outcome)
        return {"ok": True}


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"直播回复结果缺少 {key}")
    return value.strip()


def _read_result(payload: dict[str, Any], key: str) -> OutputResult:
    value: Any = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"直播回复结果 {key} 无效")
    result: dict[str, Any] = value
    status: Any = result.get("status")
    if status not in _STATUSES:
        raise ValueError(f"直播回复结果 {key} 无效")
    return OutputResult(status=status, error=str(result.get("error", "")))


async def log_failed_outcome(outcome: LiveReplyOutcome) -> None:
    """Diagnostic listener: a live reply that was not shown or not heard."""
    for channel, result in (("bubble", outcome.bubble), ("speech", outcome.speech)):
        if result.status == "failed":
            logger.warning(
                "live reply %s (run %s) %s failed: %s",
                outcome.reply_id,
                outcome.run_id,
                channel,
                result.error,
            )
