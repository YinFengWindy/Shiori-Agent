"""Observable state of one live run, as served by ``live.status``.

Errors are *current* conditions, cleared when they recover:
``connection_error`` clears once the stream is connected again and
``reply_error`` once a later reply is output without a failed path.
``stop_reason`` explains a stopped run. Reply records carry ids and per-path
results only — never danmaku text or sender — so status keeps nothing of
messages that were not replied to.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .bilibili_live_api import LiveRoom
from .live_output import LiveReplyOutcome, OutputResult

# How many recent replies the status keeps for display.
RECENT_REPLY_LIMIT = 10


class RunState(StrEnum):
    """Whether the run processes danmaku; ``idle`` means no run exists."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class ConnectionState(StrEnum):
    """The danmaku stream connection."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"
    # Bilibili refused the room, the stream or its request.
    REJECTED = "rejected"
    # The login is missing, rejected, or the stream delivered anonymized senders.
    LOGIN_INVALID = "login_invalid"


class LiveCounter(StrEnum):
    """Per-run counters; every one is always present in a status."""

    RECEIVED = "received"
    # New danmaku that arrived while paused and were dropped unprocessed.
    DROPPED_PAUSED = "dropped_paused"
    REDELIVERED = "redelivered"
    DUPLICATES = "duplicates"
    BUSY = "busy"
    EXPIRED = "expired"
    EVICTED = "evicted"
    REPLIED = "replied"
    GENERATION_FAILED = "generation_failed"
    UNREADABLE = "unreadable"


@dataclass
class ReplyRecord:
    """What became of one generation attempt and its output paths."""

    reply_id: str
    generation: str
    error: str = ""
    bubble: OutputResult | None = None
    speech: OutputResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Wire form; an output path is ``None`` until its outcome arrives."""
        return {
            "reply_id": self.reply_id,
            "generation": self.generation,
            "error": self.error,
            "bubble": _result(self.bubble),
            "speech": _result(self.speech),
        }


def status_shape(role_id: str, **values: Any) -> dict[str, Any]:
    """The one ``live.status`` shape; an idle role gets nulls and zeros."""
    return {
        "role_id": role_id,
        "state": RunState.IDLE.value,
        "connection": None,
        "room": None,
        "run_id": None,
        "queue_length": 0,
        "generating": False,
        "output_pending": False,
        "connection_error": "",
        "reply_error": "",
        "stop_reason": "",
        "counters": {counter.value: 0 for counter in LiveCounter},
        "recent": [],
        **values,
    }


class LiveStatus:
    """Mutable run state; the session updates it, ``snapshot`` reads it."""

    def __init__(self, role_id: str, room: LiveRoom) -> None:
        self.role_id = role_id
        self.room = room
        self.state = RunState.RUNNING
        self.connection = ConnectionState.CONNECTING
        self.run_id = ""
        self.connection_error = ""
        self.reply_error = ""
        self.stop_reason = ""
        self.counters = {counter: 0 for counter in LiveCounter}
        self._recent: OrderedDict[str, ReplyRecord] = OrderedDict()

    def count(self, counter: LiveCounter, amount: int = 1) -> None:
        """Add to one counter."""
        self.counters[counter] += amount

    def connected(self) -> None:
        """The stream is live again; its error has recovered."""
        self.connection = ConnectionState.CONNECTED
        self.connection_error = ""

    def connection_failed(self, state: ConnectionState, error: str) -> None:
        """The stream failed; ``state`` says whether it is retried."""
        self.connection = state
        self.connection_error = error

    def generated(self, reply_id: str) -> None:
        """A reply was generated and handed to the pet."""
        self.count(LiveCounter.REPLIED)
        self._remember(ReplyRecord(reply_id=reply_id, generation="replied"))

    def generation_failed(self, reply_id: str, error: str) -> None:
        """No reply text: nothing is shown or spoken."""
        self.count(LiveCounter.GENERATION_FAILED)
        self.reply_error = error
        self._remember(ReplyRecord(reply_id, generation="failed", error=error))

    def output_finished(self, outcome: LiveReplyOutcome) -> None:
        """Record the bubble and speech results of a reply of this run."""
        record = self._recent.get(outcome.reply_id)
        if record is None:
            return
        record.bubble, record.speech = outcome.bubble, outcome.speech
        paths = (("气泡", outcome.bubble), ("语音", outcome.speech))
        failures = [
            f"{name}输出失败: {result.error}"
            for name, result in paths
            if result.status == "failed"
        ]
        # A cancelled reply proves nothing either way and leaves the error as is.
        if failures:
            self.reply_error = "；".join(failures)
        elif outcome.bubble.status != "cancelled":
            self.reply_error = ""

    def output_lost(self, reply_id: str, error: str) -> None:
        """The reply's outcome did not arrive (in time); its paths stay unknown."""
        record = self._recent.get(reply_id)
        if record is not None:
            record.error = error
        self.reply_error = error

    def snapshot(self, **live: Any) -> dict[str, Any]:
        """Wire form for ``live.status``; ``live`` adds queue and in-flight facts."""
        return status_shape(
            self.role_id,
            state=self.state.value,
            connection=self.connection.value,
            room={"room_id": self.room.room_id, "title": self.room.title},
            run_id=self.run_id,
            connection_error=self.connection_error,
            reply_error=self.reply_error,
            stop_reason=self.stop_reason,
            counters={key.value: value for key, value in self.counters.items()},
            recent=[record.to_dict() for record in reversed(self._recent.values())],
            **live,
        )

    def _remember(self, record: ReplyRecord) -> None:
        self._recent[record.reply_id] = record
        while len(self._recent) > RECENT_REPLY_LIMIT:
            self._recent.popitem(last=False)


def _result(result: OutputResult | None) -> dict[str, str] | None:
    return None if result is None else {"status": result.status, "error": result.error}
