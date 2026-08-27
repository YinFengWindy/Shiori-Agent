"""角色关系快照模型与规范化 helper。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FIRST_PERSON_MARKERS = ("我", "自己")
_MAX_RELATION_TAGS = 4
_RECENT_MESSAGE_LIMIT = 12
_RECENT_MESSAGE_CHAR_LIMIT = 6000

_RELATION_STATE_KEYS = (
    "closeness",
    "dependence",
    "security",
    "initiative_desire",
    "neglect_sensitivity",
)
_BEHAVIOR_PROFILE_KEYS = (
    "loneliness_growth_base",
    "loneliness_growth_when_unanswered",
    "trigger_threshold",
    "post_trigger_cooldown_minutes",
    "night_suppression",
)
_DEFAULT_RELATION_STATE = {
    "closeness": 0.5,
    "dependence": 0.45,
    "security": 0.5,
    "initiative_desire": 0.5,
    "neglect_sensitivity": 0.5,
}
_DEFAULT_BEHAVIOR_PROFILE = {
    "loneliness_growth_base": 1.6,
    "loneliness_growth_when_unanswered": 2.4,
    "trigger_threshold": 68.0,
    "post_trigger_cooldown_minutes": 240,
    "night_suppression": 0.4,
}

@dataclass(frozen=True)
class RelationshipSnapshot:
    role_id: str
    role_self_view: str
    relation_tags: list[str]
    relation_state: dict[str, float]
    behavior_profile: dict[str, float | int]
    source_summary: dict[str, Any]
    generated_at: str
    last_attempted_at: str
    last_source_message_count: int
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_self_view": self.role_self_view,
            "relation_tags": list(self.relation_tags),
            "internal_profile": {
                "relation_state": dict(self.relation_state),
                "behavior_profile": dict(self.behavior_profile),
            },
            "source_summary": dict(self.source_summary),
            "generated_at": self.generated_at,
            "last_attempted_at": self.last_attempted_at,
            "last_source_message_count": self.last_source_message_count,
            "last_error": self.last_error,
        }

def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

def _normalize_tags(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    tags: list[str] = []
    for item in raw:
        tag = str(item or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= _MAX_RELATION_TAGS:
            break
    return tags


def _normalize_relation_state(raw: object) -> dict[str, float]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        key: _clamp(float(payload.get(key, _DEFAULT_RELATION_STATE[key]) or _DEFAULT_RELATION_STATE[key]), 0.0, 1.0)
        for key in _RELATION_STATE_KEYS
    }


def _normalize_behavior_profile(raw: object) -> dict[str, float | int]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "loneliness_growth_base": _clamp(
            float(payload.get("loneliness_growth_base", _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_base"]) or _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_base"]),
            _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_base"],
            8.0,
        ),
        "loneliness_growth_when_unanswered": _clamp(
            float(payload.get("loneliness_growth_when_unanswered", _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_when_unanswered"]) or _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_when_unanswered"]),
            _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_when_unanswered"],
            12.0,
        ),
        "trigger_threshold": _clamp(
            float(payload.get("trigger_threshold", _DEFAULT_BEHAVIOR_PROFILE["trigger_threshold"]) or _DEFAULT_BEHAVIOR_PROFILE["trigger_threshold"]),
            0.0,
            100.0,
        ),
        "post_trigger_cooldown_minutes": int(
            _clamp(
                float(payload.get("post_trigger_cooldown_minutes", _DEFAULT_BEHAVIOR_PROFILE["post_trigger_cooldown_minutes"]) or _DEFAULT_BEHAVIOR_PROFILE["post_trigger_cooldown_minutes"]),
                1.0,
                24 * 60,
            )
        ),
        "night_suppression": _clamp(
            float(payload.get("night_suppression", _DEFAULT_BEHAVIOR_PROFILE["night_suppression"]) or _DEFAULT_BEHAVIOR_PROFILE["night_suppression"]),
            0.0,
            1.0,
        ),
    }


def _is_first_person_self_view(text: str) -> bool:
    clean = str(text or "").strip()
    return bool(clean and any(marker in clean for marker in _FIRST_PERSON_MARKERS))
