"""角色寂寞状态模型与离散时间推进 helper。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

_UNANSWERED_REPLY_WINDOW_HOURS = 24
_NIGHT_SUPPRESSION_START_HOUR = 0
_NIGHT_SUPPRESSION_END_HOUR = 6
_LONELINESS_TICK_MINUTES = 10
_PROACTIVE_CLOSENESS_THRESHOLD = 0.7

@dataclass(frozen=True)
class LonelinessRuntimeState:
    role_id: str
    loneliness_value: float
    last_calculated_at: str
    last_user_at: str
    last_proactive_at: str
    awaiting_reply_after_proactive: bool
    awaiting_reply_since: str
    last_triggered_at: str
    cooldown_until: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now().astimezone()).astimezone().isoformat()


def _parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _advance_by_loneliness_ticks(
    last_calculated: datetime,
    *,
    tick_count: int,
) -> datetime:
    return last_calculated + timedelta(minutes=max(0, tick_count) * _LONELINESS_TICK_MINUTES)


def _loneliness_tick_count(
    last_calculated: datetime,
    *,
    now: datetime,
) -> int:
    elapsed_seconds = max(0.0, (now - last_calculated).total_seconds())
    return int(elapsed_seconds // (_LONELINESS_TICK_MINUTES * 60))
