from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agent.llm_json import load_json_object_loose
from agent.provider import LLMProvider
from core.memory.markdown import resolve_markdown_store
from infra.persistence.json_store import atomic_save_json, load_json
from session.manager import SessionManager

from .store import RoleRecord, RoleStore

_SNAPSHOT_FILE = "relationship_snapshot.json"
_RUNTIME_FILE = "loneliness_runtime.json"
_FIRST_PERSON_MARKERS = ("我", "自己")
_MAX_RELATION_TAGS = 4
_RECENT_MESSAGE_LIMIT = 12
_RECENT_MESSAGE_CHAR_LIMIT = 6000
_UNANSWERED_REPLY_WINDOW_HOURS = 24
_NIGHT_SUPPRESSION_START_HOUR = 0
_NIGHT_SUPPRESSION_END_HOUR = 6
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
    "loneliness_growth_base": 1.2,
    "loneliness_growth_when_unanswered": 1.8,
    "trigger_threshold": 68.0,
    "post_trigger_cooldown_minutes": 240,
    "night_suppression": 0.4,
}
_RELATIONSHIP_SYSTEM = (
    "你正在根据当前关系证据，生成角色此刻对用户关系的主观状态。"
    "你只能输出 JSON 对象，不要输出 JSON 之外的文字。"
)
_RELATIONSHIP_PROMPT = """\
你要为当前角色生成一份运行时关系快照。

硬规则：
- `role_self_view` 必须是角色第一人称内心想法，必须使用“我”来表达，不能写成旁白或上帝视角。
- `relation_tags` 只能给 1 到 4 个短标签。
- `relation_state` 只能包含以下字段：closeness、dependence、security、initiative_desire、neglect_sensitivity。
- `relation_state` 每个字段都必须是 0 到 1 的数字。
- `behavior_profile` 只能包含以下字段：loneliness_growth_base、loneliness_growth_when_unanswered、trigger_threshold、post_trigger_cooldown_minutes、night_suppression。
- `trigger_threshold` 使用 0 到 100 的数值。
- `night_suppression` 使用 0 到 1 的数值。
- 不要复述静态设定，不要分析系统机制，不要出现“角色”“用户”“设定”等旁白口吻。

输出 JSON 结构：
{
  "role_self_view": "第一人称想法",
  "relation_tags": ["标签1", "标签2"],
  "relation_state": {
    "closeness": 0.0,
    "dependence": 0.0,
    "security": 0.0,
    "initiative_desire": 0.0,
    "neglect_sensitivity": 0.0
  },
  "behavior_profile": {
    "loneliness_growth_base": 0.0,
    "loneliness_growth_when_unanswered": 0.0,
    "trigger_threshold": 0.0,
    "post_trigger_cooldown_minutes": 0,
    "night_suppression": 0.0
  }
}

角色名称：
{role_name}

角色简介：
{role_description}

当前 SELF.md：
{self_text}

当前关系相关 MEMORY.md：
{memory_text}

最近互动：
{recent_messages}

主动互动摘要：
{interaction_summary}
"""


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
            "last_error": self.last_error,
        }


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
            0.1,
            8.0,
        ),
        "loneliness_growth_when_unanswered": _clamp(
            float(payload.get("loneliness_growth_when_unanswered", _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_when_unanswered"]) or _DEFAULT_BEHAVIOR_PROFILE["loneliness_growth_when_unanswered"]),
            0.1,
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


class RoleRelationshipRuntimeService:
    """Owns role runtime relationship snapshot and loneliness state."""

    def __init__(
        self,
        workspace: Path,
        *,
        role_store: RoleStore,
        session_manager: SessionManager,
        presence,
    ) -> None:
        self._workspace = Path(workspace)
        self._role_store = role_store
        self._session_manager = session_manager
        self._presence = presence

    def state_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / str(role_id).strip() / "state"

    def snapshot_path(self, role_id: str) -> Path:
        return self.state_root(role_id) / _SNAPSHOT_FILE

    def runtime_path(self, role_id: str) -> Path:
        return self.state_root(role_id) / _RUNTIME_FILE

    def read_snapshot(self, role_id: str) -> dict[str, Any] | None:
        payload = load_json(self.snapshot_path(role_id), default=None, domain="role.relationship")
        if not isinstance(payload, dict):
            return None
        return self._normalize_snapshot_payload(role_id=role_id, payload=payload, preserve_error=True)

    def read_loneliness_runtime(self, role_id: str) -> dict[str, Any] | None:
        payload = load_json(self.runtime_path(role_id), default=None, domain="role.loneliness")
        if not isinstance(payload, dict):
            return None
        return self._normalize_runtime_payload(role_id=role_id, payload=payload)

    def write_snapshot(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_snapshot_payload(role_id=role_id, payload=payload, preserve_error=True)
        path = self.snapshot_path(role_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(path, normalized, domain="role.relationship")
        return normalized

    def write_loneliness_runtime(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_runtime_payload(role_id=role_id, payload=payload)
        path = self.runtime_path(role_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(path, normalized, domain="role.loneliness")
        return normalized

    def mark_snapshot_error(
        self,
        role_id: str,
        *,
        error: str,
        attempted_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = attempted_at or datetime.now().astimezone()
        existing = self.read_snapshot(role_id) or {}
        existing["last_attempted_at"] = _now_iso(now)
        existing["last_error"] = str(error or "").strip()
        return self.write_snapshot(role_id, existing)

    def generate_snapshot_input(
        self,
        role_id: str,
    ) -> dict[str, Any]:
        role = self._role_store.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        store = resolve_markdown_store(workspace=self._workspace, role_id=role_id)
        session = self._session_manager.get_or_create(self._session_manager.role_session_key(role_id))
        recent_messages = self._collect_recent_messages(session.messages)
        return {
            "role": role,
            "self_text": store.read_self().strip(),
            "memory_text": store.read_long_term().strip(),
            "recent_messages": recent_messages,
            "interaction_summary": self._build_interaction_summary(role_id=role_id, recent_messages=recent_messages),
        }

    async def generate_snapshot_via_llm(
        self,
        role_id: str,
        *,
        provider: LLMProvider,
        model: str,
        max_tokens: int = 2048,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        source = self.generate_snapshot_input(role_id)
        role = source["role"]
        recent_messages = source["recent_messages"]
        now_dt = now or datetime.now().astimezone()
        prompt = _RELATIONSHIP_PROMPT.format(
            role_name=role.name or role.id,
            role_description=role.description.strip() or "（无）",
            self_text=source["self_text"] or "（空）",
            memory_text=source["memory_text"] or "（空）",
            recent_messages=self._render_recent_messages(recent_messages),
            interaction_summary=source["interaction_summary"],
        )
        response = await provider.chat(
            messages=[
                {"role": "system", "content": _RELATIONSHIP_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            tools=[],
            model=model,
            max_tokens=max_tokens,
        )
        payload = load_json_object_loose((response.content or "").strip())
        if not isinstance(payload, dict):
            raise ValueError("relationship snapshot 必须返回 JSON 对象")
        snapshot = self._normalize_snapshot_payload(
            role_id=role_id,
            payload={
                "role_id": role_id,
                "role_self_view": payload.get("role_self_view"),
                "relation_tags": payload.get("relation_tags"),
                "internal_profile": {
                    "relation_state": payload.get("relation_state"),
                    "behavior_profile": payload.get("behavior_profile"),
                },
                "source_summary": {
                    "recent_message_count": len(recent_messages),
                    "memory_sections": ["SELF.md", "MEMORY.md"],
                    "generated_from_window_hours": 72,
                },
                "generated_at": _now_iso(now_dt),
                "last_attempted_at": _now_iso(now_dt),
                "last_error": "",
            },
            preserve_error=False,
        )
        return self.write_snapshot(role_id, snapshot)

    def recompute_loneliness(self, role_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return None
        now_dt = (now or datetime.now().astimezone()).astimezone()
        current = self.read_loneliness_runtime(role_id) or self._build_initial_runtime(role_id, now=now_dt)
        value = float(current["loneliness_value"])
        last_calculated = _parse_iso(current.get("last_calculated_at")) or now_dt
        elapsed_minutes = max(0.0, (now_dt - last_calculated).total_seconds() / 60.0)
        profile = self._behavior_profile(snapshot)
        delta = (elapsed_minutes / 60.0) * float(profile["loneliness_growth_base"])
        if bool(current.get("awaiting_reply_after_proactive")):
            awaiting_since = _parse_iso(current.get("awaiting_reply_since"))
            if awaiting_since is not None and now_dt - awaiting_since <= timedelta(hours=_UNANSWERED_REPLY_WINDOW_HOURS):
                delta += (elapsed_minutes / 60.0) * float(profile["loneliness_growth_when_unanswered"])
            else:
                current["awaiting_reply_after_proactive"] = False
                current["awaiting_reply_since"] = ""
        current["loneliness_value"] = round(_clamp(value + delta, 0.0, 100.0), 2)
        current["last_calculated_at"] = _now_iso(now_dt)
        presence_key = self._session_manager.role_session_key(role_id)
        last_user_at = self._presence.get_last_user_at(presence_key) if self._presence else None
        last_proactive_at = self._presence.get_last_proactive_at(presence_key) if self._presence else None
        current["last_user_at"] = _now_iso(last_user_at) if last_user_at else str(current.get("last_user_at") or "")
        current["last_proactive_at"] = _now_iso(last_proactive_at) if last_proactive_at else str(current.get("last_proactive_at") or "")
        return self.write_loneliness_runtime(role_id, current)

    def handle_user_message(self, session_key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return None
        now_dt = (now or datetime.now().astimezone()).astimezone()
        current = self.recompute_loneliness(role_id, now=now_dt) or self._build_initial_runtime(role_id, now=now_dt)
        security = float(self._relation_state(snapshot)["security"])
        if security >= 0.7:
            drop_ratio = 0.35
        elif security >= 0.4:
            drop_ratio = 0.45
        else:
            drop_ratio = 0.55
        current["loneliness_value"] = round(_clamp(float(current["loneliness_value"]) * (1.0 - drop_ratio), 0.0, 100.0), 2)
        current["awaiting_reply_after_proactive"] = False
        current["awaiting_reply_since"] = ""
        current["last_calculated_at"] = _now_iso(now_dt)
        current["last_user_at"] = _now_iso(now_dt)
        return self.write_loneliness_runtime(role_id, current)

    def handle_proactive_sent(self, session_key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return None
        now_dt = (now or datetime.now().astimezone()).astimezone()
        current = self.recompute_loneliness(role_id, now=now_dt) or self._build_initial_runtime(role_id, now=now_dt)
        cooldown_minutes = int(self._behavior_profile(snapshot)["post_trigger_cooldown_minutes"])
        current["awaiting_reply_after_proactive"] = True
        current["awaiting_reply_since"] = _now_iso(now_dt)
        current["last_triggered_at"] = _now_iso(now_dt)
        current["last_proactive_at"] = _now_iso(now_dt)
        current["cooldown_until"] = _now_iso(now_dt + timedelta(minutes=cooldown_minutes))
        current["last_calculated_at"] = _now_iso(now_dt)
        return self.write_loneliness_runtime(role_id, current)

    def should_trigger_proactive(
        self,
        session_key: str,
        *,
        now: datetime | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return False, {"reason": "no_role"}
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return False, {"reason": "no_snapshot"}
        runtime = self.recompute_loneliness(role_id, now=now)
        if runtime is None:
            return False, {"reason": "no_runtime"}
        now_dt = (now or datetime.now().astimezone()).astimezone()
        effective_value = float(runtime["loneliness_value"])
        local_hour = now_dt.hour
        if _NIGHT_SUPPRESSION_START_HOUR <= local_hour < _NIGHT_SUPPRESSION_END_HOUR:
            effective_value *= float(self._behavior_profile(snapshot)["night_suppression"])
        threshold = float(self._behavior_profile(snapshot)["trigger_threshold"])
        cooldown_until = _parse_iso(runtime.get("cooldown_until"))
        if cooldown_until is not None and cooldown_until > now_dt:
            return False, {
                "reason": "cooldown",
                "loneliness_value": runtime["loneliness_value"],
                "effective_loneliness_value": round(effective_value, 2),
                "trigger_threshold": threshold,
            }
        return effective_value >= threshold, {
            "reason": "threshold" if effective_value >= threshold else "below_threshold",
            "loneliness_value": runtime["loneliness_value"],
            "effective_loneliness_value": round(effective_value, 2),
            "trigger_threshold": threshold,
        }

    def enrich_session_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        next_metadata = dict(metadata or {})
        role_id = str(next_metadata.get("role_id") or "").strip()
        if not role_id:
            return next_metadata
        snapshot = self.read_snapshot(role_id)
        runtime = self.read_loneliness_runtime(role_id)
        if snapshot is not None:
            next_metadata["relationship_snapshot"] = snapshot
        if runtime is not None:
            next_metadata["loneliness_runtime"] = runtime
        return next_metadata

    def _behavior_profile(self, snapshot: dict[str, Any]) -> dict[str, float | int]:
        internal = snapshot.get("internal_profile") if isinstance(snapshot, dict) else {}
        return _normalize_behavior_profile((internal or {}).get("behavior_profile"))

    def _relation_state(self, snapshot: dict[str, Any]) -> dict[str, float]:
        internal = snapshot.get("internal_profile") if isinstance(snapshot, dict) else {}
        return _normalize_relation_state((internal or {}).get("relation_state"))

    def _build_initial_runtime(self, role_id: str, *, now: datetime) -> dict[str, Any]:
        session_key = self._session_manager.role_session_key(role_id)
        last_user_at = self._presence.get_last_user_at(session_key) if self._presence else None
        last_proactive_at = self._presence.get_last_proactive_at(session_key) if self._presence else None
        return self._normalize_runtime_payload(
            role_id=role_id,
            payload={
                "role_id": role_id,
                "loneliness_value": 0.0,
                "last_calculated_at": _now_iso(now),
                "last_user_at": _now_iso(last_user_at) if last_user_at else "",
                "last_proactive_at": _now_iso(last_proactive_at) if last_proactive_at else "",
                "awaiting_reply_after_proactive": False,
                "awaiting_reply_since": "",
                "last_triggered_at": "",
                "cooldown_until": "",
            },
        )

    def _normalize_snapshot_payload(
        self,
        *,
        role_id: str,
        payload: dict[str, Any],
        preserve_error: bool,
    ) -> dict[str, Any]:
        internal = payload.get("internal_profile") if isinstance(payload.get("internal_profile"), dict) else {}
        role_self_view = str(payload.get("role_self_view") or "").strip()
        if role_self_view and not _is_first_person_self_view(role_self_view):
            raise ValueError("relationship snapshot 必须使用第一人称角色视角")
        normalized = {
            "role_id": role_id,
            "role_self_view": role_self_view,
            "relation_tags": _normalize_tags(payload.get("relation_tags")),
            "internal_profile": {
                "relation_state": _normalize_relation_state(internal.get("relation_state")),
                "behavior_profile": _normalize_behavior_profile(internal.get("behavior_profile")),
            },
            "source_summary": dict(payload.get("source_summary") or {}),
            "generated_at": str(payload.get("generated_at") or ""),
            "last_attempted_at": str(payload.get("last_attempted_at") or payload.get("generated_at") or ""),
            "last_error": str(payload.get("last_error") or "") if preserve_error else "",
        }
        return normalized

    def _normalize_runtime_payload(self, *, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "role_id": role_id,
            "loneliness_value": round(_clamp(float(payload.get("loneliness_value", 0.0) or 0.0), 0.0, 100.0), 2),
            "last_calculated_at": str(payload.get("last_calculated_at") or ""),
            "last_user_at": str(payload.get("last_user_at") or ""),
            "last_proactive_at": str(payload.get("last_proactive_at") or ""),
            "awaiting_reply_after_proactive": bool(payload.get("awaiting_reply_after_proactive")),
            "awaiting_reply_since": str(payload.get("awaiting_reply_since") or ""),
            "last_triggered_at": str(payload.get("last_triggered_at") or ""),
            "cooldown_until": str(payload.get("cooldown_until") or ""),
        }

    def _role_id_from_session_key(self, session_key: str) -> str:
        clean_key = str(session_key or "").strip()
        if clean_key.startswith("role:"):
            return clean_key.split(":", 1)[1]
        session = self._session_manager.get_or_create(clean_key)
        return str(session.metadata.get("role_id") or "").strip()

    def _collect_recent_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        pairs: list[dict[str, str]] = []
        total_chars = 0
        for message in reversed(messages):
            role = str(message.get("role") or "").strip()
            if role not in {"user", "assistant"}:
                continue
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            total_chars += len(content)
            if total_chars > _RECENT_MESSAGE_CHAR_LIMIT and pairs:
                break
            pairs.append({"role": role, "content": content})
            if len(pairs) >= _RECENT_MESSAGE_LIMIT:
                break
        pairs.reverse()
        return pairs

    def _build_interaction_summary(
        self,
        *,
        role_id: str,
        recent_messages: list[dict[str, str]],
    ) -> str:
        session_key = self._session_manager.role_session_key(role_id)
        last_user_at = self._presence.get_last_user_at(session_key) if self._presence else None
        last_proactive_at = self._presence.get_last_proactive_at(session_key) if self._presence else None
        summary_lines = [
            f"最近消息条数: {len(recent_messages)}",
            f"最近用户消息时间: {_now_iso(last_user_at) if last_user_at else '（无）'}",
            f"最近主动消息时间: {_now_iso(last_proactive_at) if last_proactive_at else '（无）'}",
        ]
        runtime = self.read_loneliness_runtime(role_id)
        if runtime is not None:
            summary_lines.append(f"当前 awaiting_reply_after_proactive: {bool(runtime.get('awaiting_reply_after_proactive'))}")
        return "\n".join(summary_lines)

    def _render_recent_messages(self, recent_messages: list[dict[str, str]]) -> str:
        if not recent_messages:
            return "（暂无近期互动）"
        return "\n".join(
            f"{'我' if item['role'] == 'assistant' else '用户'}：{item['content']}"
            for item in recent_messages
        )


class RelationshipSnapshotOptimizer:
    """Generates role relationship snapshots from current evidence."""

    def __init__(
        self,
        runtime: RoleRelationshipRuntimeService,
        *,
        provider: LLMProvider,
        model: str,
        max_tokens: int = 2048,
    ) -> None:
        self._runtime = runtime
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def optimize(self, *, role_id: str) -> dict[str, Any] | None:
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id required for relationship optimizer")
        async with self._lock:
            now = datetime.now().astimezone()
            try:
                snapshot = await self._runtime.generate_snapshot_via_llm(
                    clean_role_id,
                    provider=self._provider,
                    model=self._model,
                    max_tokens=self._max_tokens,
                    now=now,
                )
                self._runtime.recompute_loneliness(clean_role_id, now=now)
                return snapshot
            except Exception as exc:
                self._runtime.mark_snapshot_error(
                    clean_role_id,
                    error=str(exc),
                    attempted_at=now,
                )
                return None


class RelationshipSnapshotLoop:
    """Runs the relationship snapshot optimizer on overdue roles."""

    def __init__(
        self,
        optimizer: RelationshipSnapshotOptimizer,
        *,
        role_store: RoleStore,
        runtime: RoleRelationshipRuntimeService,
        interval_seconds: int = 8 * 3600,
        recent_refresh_seconds: int = 4 * 3600,
        recent_window_seconds: int = 2 * 3600,
        now_fn=None,
    ) -> None:
        self._optimizer = optimizer
        self._role_store = role_store
        self._runtime = runtime
        self._interval = max(60, int(interval_seconds))
        self._recent_refresh = max(60, int(recent_refresh_seconds))
        self._recent_window = max(60, int(recent_window_seconds))
        self._now_fn = now_fn or datetime.now
        self._running = False

    async def run(self) -> None:
        self._running = True
        await self._catch_up_overdue_roles()
        while self._running:
            await asyncio.sleep(self._seconds_until_next_tick())
            if not self._running:
                break
            for role in self._role_store.list_roles():
                if not self._is_role_overdue(role.id, now=self._now_fn().astimezone()):
                    continue
                await self._optimizer.optimize(role_id=role.id)

    def stop(self) -> None:
        self._running = False

    async def _catch_up_overdue_roles(self) -> None:
        now = self._now_fn().astimezone()
        for role in self._role_store.list_roles():
            if self._is_role_overdue(role.id, now=now):
                await self._optimizer.optimize(role_id=role.id)

    def _is_role_overdue(self, role_id: str, *, now: datetime) -> bool:
        snapshot = self._runtime.read_snapshot(role_id)
        if snapshot is None:
            return True
        generated_at = _parse_iso(snapshot.get("generated_at"))
        if generated_at is None:
            return True
        last_activity = self._latest_activity(role_id)
        if last_activity is not None and (now - last_activity).total_seconds() <= self._recent_window:
            return (now - generated_at).total_seconds() >= self._recent_refresh
        return (now - generated_at).total_seconds() >= self._interval

    def _latest_activity(self, role_id: str) -> datetime | None:
        session_key = self._runtime._session_manager.role_session_key(role_id)
        last_user = self._runtime._presence.get_last_user_at(session_key) if self._runtime._presence else None
        last_proactive = self._runtime._presence.get_last_proactive_at(session_key) if self._runtime._presence else None
        if last_user is None:
            return last_proactive
        if last_proactive is None:
            return last_user
        return max(last_user, last_proactive)

    def _seconds_until_next_tick(self) -> float:
        now = self._now_fn()
        now_ts = now.replace(second=0, microsecond=0).timestamp()
        next_ts = (now_ts // self._interval + 1) * self._interval
        return max(1.0, next_ts - now.timestamp())


class LonelinessHeartbeatLoop:
    """Periodically refreshes per-role loneliness runtime values."""

    def __init__(
        self,
        runtime: RoleRelationshipRuntimeService,
        *,
        role_store: RoleStore,
        interval_seconds: int = 10 * 60,
    ) -> None:
        self._runtime = runtime
        self._role_store = role_store
        self._interval = max(30, int(interval_seconds))
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            now = datetime.now().astimezone()
            for role in self._role_store.list_roles():
                self._runtime.recompute_loneliness(role.id, now=now)

    def stop(self) -> None:
        self._running = False
