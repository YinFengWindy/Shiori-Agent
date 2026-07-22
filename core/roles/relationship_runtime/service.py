"""角色关系快照生成、寂寞状态与场景追问服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from agent.llm_json import load_json_object_loose
from agent.provider import LLMProvider
from core.memory.markdown import resolve_markdown_store
from session.manager import SessionManager

from ..scene_followup_runtime import SceneFollowupRuntime, SceneTransition
from ..store import RoleStore
from .loneliness import (
    _NIGHT_SUPPRESSION_END_HOUR,
    _NIGHT_SUPPRESSION_START_HOUR,
    _PROACTIVE_CLOSENESS_THRESHOLD,
    _UNANSWERED_REPLY_WINDOW_HOURS,
    _advance_by_loneliness_ticks,
    _loneliness_tick_count,
    _now_iso,
    _parse_iso,
)
from .models import (
    _RECENT_MESSAGE_CHAR_LIMIT,
    _RECENT_MESSAGE_LIMIT,
    _clamp,
    _is_first_person_self_view,
    _normalize_behavior_profile,
    _normalize_relation_state,
    _normalize_tags,
)
from .persistence import _RelationshipPersistenceMixin
from .snapshot import _RELATIONSHIP_PROMPT, _RELATIONSHIP_SYSTEM

class RoleRelationshipRuntimeService(_RelationshipPersistenceMixin):
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
        self._scene_followup = SceneFollowupRuntime(workspace)

    def current_loneliness_runtime(self, role_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        """Returns the latest loneliness runtime, catching up elapsed time when possible."""
        runtime = self.recompute_loneliness(role_id, now=now)
        if runtime is not None:
            return runtime
        return self.read_loneliness_runtime(role_id)

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
            "session_message_count": self._count_session_messages(session.messages),
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
        session_message_count = int(source["session_message_count"])
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
                "last_source_message_count": session_message_count,
                "last_error": "",
            },
            preserve_error=False,
        )
        return self.write_snapshot(role_id, snapshot)

    async def refresh_snapshot_after_consolidation(
        self,
        session: object,
        *,
        optimizer: "RelationshipSnapshotOptimizer",
    ) -> dict[str, Any] | None:
        """Refreshes the role snapshot after consolidation when the session is role-bound."""
        role_id = self._role_id_from_session(session)
        if not role_id or self._role_store.get_role(role_id) is None:
            return None
        snapshot = await optimizer.optimize(role_id=role_id)
        metadata = getattr(session, "metadata", None)
        if isinstance(metadata, dict):
            if snapshot is None:
                session.metadata = self.enrich_session_metadata(metadata)
            else:
                next_metadata = dict(metadata)
                next_metadata["relationship_snapshot"] = snapshot
                runtime = self.current_loneliness_runtime(role_id)
                if runtime is not None:
                    next_metadata["loneliness_runtime"] = runtime
                session.metadata = next_metadata
        return snapshot

    def recompute_loneliness(self, role_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return None
        now_dt = (now or datetime.now().astimezone()).astimezone()
        current = self.read_loneliness_runtime(role_id) or self._build_initial_runtime(role_id, now=now_dt)
        if not self._is_loneliness_growth_enabled(snapshot):
            self._clear_awaiting_reply_state(current)
            current["last_calculated_at"] = _now_iso(now_dt)
            return self._write_runtime_with_presence(role_id, current)
        value = float(current["loneliness_value"])
        last_calculated = _parse_iso(current.get("last_calculated_at")) or now_dt
        profile = self._behavior_profile(snapshot)
        tick_count = _loneliness_tick_count(last_calculated, now=now_dt)
        delta = tick_count * float(profile["loneliness_growth_base"])
        if bool(current.get("awaiting_reply_after_proactive")):
            awaiting_since = _parse_iso(current.get("awaiting_reply_since"))
            if awaiting_since is not None and now_dt - awaiting_since <= timedelta(hours=_UNANSWERED_REPLY_WINDOW_HOURS):
                delta += tick_count * float(profile["loneliness_growth_when_unanswered"])
            else:
                self._clear_awaiting_reply_state(current)
        current["loneliness_value"] = round(_clamp(value + delta, 0.0, 100.0), 2)
        if tick_count > 0:
            current["last_calculated_at"] = _now_iso(
                _advance_by_loneliness_ticks(last_calculated, tick_count=tick_count)
            )
        return self._write_runtime_with_presence(role_id, current)

    def handle_user_message(self, session_key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        snapshot = self.read_snapshot(role_id)
        if snapshot is None:
            return None
        now_dt = (now or datetime.now().astimezone()).astimezone()
        current = self.recompute_loneliness(role_id, now=now_dt) or self._build_initial_runtime(role_id, now=now_dt)
        self._scene_followup.handle_user_message(session_key, now=now_dt)
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

    def should_trigger_scene_followup(
        self,
        session_key: str,
        now: datetime | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Returns whether a same-scene follow-up may bypass loneliness."""
        return self._scene_followup.should_trigger(session_key, now)

    def handle_scene_followup_sent(
        self,
        session_key: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Advances same-scene scheduling after successful delivery."""
        return self._scene_followup.handle_followup_sent(session_key, now=now)

    def close_scene_followup(self, session_key: str) -> None:
        """Closes same-scene scheduling after semantic scene change."""
        self._scene_followup.close(session_key)

    def apply_scene_decision(
        self,
        session_key: str,
        scene_transition: str,
        scene_key: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Applies a shared scene decision to the active follow-up state."""
        if scene_transition not in {"started", "same", "changed", "closed", "none"}:
            raise ValueError(f"unsupported scene transition: {scene_transition}")
        return self._scene_followup.apply_scene_decision(
            session_key,
            cast(SceneTransition, scene_transition),
            scene_key,
            now=now,
        )

    def should_trigger_proactive(
        self,
        session_key: str,
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
        if not self._is_loneliness_growth_enabled(snapshot):
            return False, {"reason": "not_close_enough"}
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
        runtime = self.current_loneliness_runtime(role_id)
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

    def _is_loneliness_growth_enabled(self, snapshot: dict[str, Any]) -> bool:
        return float(self._relation_state(snapshot)["closeness"]) >= _PROACTIVE_CLOSENESS_THRESHOLD

    @staticmethod
    def _clear_awaiting_reply_state(runtime: dict[str, Any]) -> None:
        runtime["awaiting_reply_after_proactive"] = False
        runtime["awaiting_reply_since"] = ""

    def _write_runtime_with_presence(self, role_id: str, runtime: dict[str, Any]) -> dict[str, Any]:
        presence_key = self._session_manager.role_session_key(role_id)
        last_user_at = self._presence.get_last_user_at(presence_key) if self._presence else None
        last_proactive_at = self._presence.get_last_proactive_at(presence_key) if self._presence else None
        runtime["last_user_at"] = _now_iso(last_user_at) if last_user_at else str(runtime.get("last_user_at") or "")
        runtime["last_proactive_at"] = _now_iso(last_proactive_at) if last_proactive_at else str(runtime.get("last_proactive_at") or "")
        return self.write_loneliness_runtime(role_id, runtime)

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
            "last_source_message_count": self._normalize_message_count(
                payload.get("last_source_message_count")
            ),
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

    def _role_id_from_session(self, session: object) -> str:
        key = str(getattr(session, "key", "") or "").strip()
        if key.startswith("role:"):
            return key.split(":", 1)[1]
        metadata = getattr(session, "metadata", None)
        if isinstance(metadata, dict):
            return str(metadata.get("role_id") or "").strip()
        return ""

    @staticmethod
    def _count_session_messages(messages: object) -> int:
        return len(messages) if isinstance(messages, list) else 0

    @staticmethod
    def _normalize_message_count(value: object) -> int:
        if not isinstance(value, (int, float, str)):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

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
