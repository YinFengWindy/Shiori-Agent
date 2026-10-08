"""Observable state of one live run, as served by ``live.status``.

Reply records carry ids and per-path results only — never danmaku text or
sender — so status keeps nothing of messages that were not replied to.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .bilibili_live_api import LiveRoom
from .live_output import LiveReplyOutcome, OutputResult

# How many recent replies the status keeps for display.
RECENT_REPLY_LIMIT = 10


class RunState(StrEnum):
    """Whether the run processes danmaku."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class ConnectionState(StrEnum):
    """The danmaku stream connection."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"
    # The login is missing, rejected, or the stream delivered anonymized senders.
    LOGIN_INVALID = "login_invalid"


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


class LiveStatus:
    """Mutable run state; the session updates it, ``snapshot`` reads it."""

    def __init__(self, role_id: str, room: LiveRoom) -> None:
        self.role_id = role_id
        self.room = room
        self.state = RunState.RUNNING
        self.connection = ConnectionState.CONNECTING
        self.run_id = ""
        self.last_error = ""
        self.stop_reason = ""
        self.counters: Counter[str] = Counter()
        self._recent: OrderedDict[str, ReplyRecord] = OrderedDict()

    def count(self, name: str, amount: int = 1) -> None:
        """Add to a named counter (received, duplicates, expired, evicted, ...)."""
        if amount:
            self.counters[name] += amount

    def fail(self, error: str) -> None:
        """Remember the latest error for display."""
        self.last_error = error

    def generated(self, reply_id: str) -> None:
        """A reply was generated and handed to the pet."""
        self.count("replied")
        self._remember(ReplyRecord(reply_id=reply_id, generation="replied"))

    def generation_failed(self, reply_id: str, error: str) -> None:
        """No reply text: nothing is shown or spoken."""
        self.count("generation_failed")
        self.fail(error)
        self._remember(ReplyRecord(reply_id, generation="failed", error=error))

    def output_finished(self, outcome: LiveReplyOutcome) -> None:
        """Record the bubble and speech results of a reply of this run."""
        record = self._recent.get(outcome.reply_id)
        if record is None:
            return
        record.bubble, record.speech = outcome.bubble, outcome.speech
        for channel, result in (("气泡", outcome.bubble), ("语音", outcome.speech)):
            if result.status == "failed":
                self.fail(f"{channel}输出失败: {result.error}")

    def output_lost(self, reply_id: str, error: str) -> None:
        """The reply's outcome did not arrive (in time); its paths stay unknown."""
        record = self._recent.get(reply_id)
        if record is not None:
            record.error = error
        self.fail(error)

    def snapshot(self, **live: Any) -> dict[str, Any]:
        """Wire form for ``live.status``; ``live`` adds queue and in-flight facts."""
        return {
            "role_id": self.role_id,
            "state": self.state.value,
            "connection": self.connection.value,
            "room": {"room_id": self.room.room_id, "title": self.room.title},
            "run_id": self.run_id,
            "last_error": self.last_error,
            "stop_reason": self.stop_reason,
            "counters": dict(self.counters),
            "recent": [record.to_dict() for record in reversed(self._recent.values())],
            **live,
        }

    def _remember(self, record: ReplyRecord) -> None:
        self._recent[record.reply_id] = record
        while len(self._recent) > RECENT_REPLY_LIMIT:
            self._recent.popitem(last=False)


def _result(result: OutputResult | None) -> dict[str, str] | None:
    return None if result is None else {"status": result.status, "error": result.error}
