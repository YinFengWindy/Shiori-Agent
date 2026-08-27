from __future__ import annotations

from typing import Any, cast

from agent.plugins.context import PluginKVStore
from agent.tool_hooks.types import HookOutcome

_THIRD_PERSON_PROMPT_TERMS = (
    "third-person view",
    "cinematic composition",
    "character visible in frame",
)
_FIRST_PERSON_NEGATIVE_TERMS = (
    "first-person view",
    "pov",
    "selfie",
)


class AutoCgPolicy:
    """Own automatic scene-CG cooldown and deduplication state."""

    _COOLDOWN_TURNS = 5
    _STATE_KEY = "auto_cg_sessions"

    def __init__(self, kv_store: PluginKVStore) -> None:
        self._kv_store = kv_store

    def advance_turn(self, session_key: str) -> None:
        """Advance the persisted user-turn counter for one conversation."""

        if not session_key.strip():
            return
        state = self._get_session_state(session_key)
        state["turn"] = int(state.get("turn", 0)) + 1
        self._set_session_state(session_key, state)

    def cooldown_remaining(self, session_key: str) -> int:
        """Return how many additional user turns remain in the cooldown."""

        state = self._get_session_state(session_key)
        turn = int(state.get("turn", 0))
        last_turn = state.get("last_success_turn")
        if not isinstance(last_turn, int):
            return 0
        return max(0, self._COOLDOWN_TURNS + 1 - (turn - last_turn))

    def guard(
        self,
        session_key: str,
        arguments: dict[str, Any],
        *,
        bypass_cooldown: bool = False,
    ) -> HookOutcome | dict[str, Any] | None:
        """Enforce cooldown and scene deduplication before an image request."""

        intent = str(arguments.get("intent") or "user_requested").strip()
        if intent != "scene_cg":
            return None
        scene_key = normalize_scene_key(arguments.get("scene_key"))
        if not scene_key:
            return HookOutcome(
                decision="deny",
                reason="scene_cg_missing_scene_key",
                extra_message="自动 CG 缺少 scene_key，请继续文字回复，不要重试。",
            )
        visual_key = normalize_scene_key(arguments.get("visual_key") or scene_key)
        state = self._get_session_state(session_key)
        turn = int(state.get("turn", 0))
        last_turn = state.get("last_success_turn")
        if (
            not bypass_cooldown
            and isinstance(last_turn, int)
            and turn - last_turn <= self._COOLDOWN_TURNS
        ):
            return HookOutcome(
                decision="deny",
                reason="scene_cg_cooldown",
                extra_message="自动 CG 仍在冷却期，请继续文字回复，不要重试。",
            )
        if visual_key == str(state.get("last_visual_key") or ""):
            return HookOutcome(
                decision="deny",
                reason="scene_cg_duplicate_visual",
                extra_message="该视觉定格已经生成过 CG，请继续文字回复，不要重复生成。",
            )
        return {
            **arguments,
            "scene_key": scene_key,
            "visual_key": visual_key,
            "prompt": _append_prompt_terms(
                arguments.get("prompt"),
                _THIRD_PERSON_PROMPT_TERMS,
            ),
            "negative_prompt": _append_prompt_terms(
                arguments.get("negative_prompt"),
                _FIRST_PERSON_NEGATIVE_TERMS,
            ),
        }

    def record_success(self, session_key: str, visual_key: object) -> None:
        """Persist cooldown and deduplication state after successful generation."""

        state = self._get_session_state(session_key)
        state["last_success_turn"] = int(state.get("turn", 0))
        state["last_visual_key"] = normalize_scene_key(visual_key)
        self._set_session_state(session_key, state)

    def _get_session_state(self, session_key: str) -> dict[str, Any]:
        raw_sessions: object = self._kv_store.get(self._STATE_KEY, {})
        sessions = (
            cast(dict[str, Any], raw_sessions) if isinstance(raw_sessions, dict) else {}
        )
        raw_state: object = sessions.get(session_key, {})
        return (
            dict(cast(dict[str, Any], raw_state)) if isinstance(raw_state, dict) else {}
        )

    def _set_session_state(self, session_key: str, state: dict[str, Any]) -> None:
        raw_sessions: object = self._kv_store.get(self._STATE_KEY, {})
        sessions = (
            cast(dict[str, Any], raw_sessions) if isinstance(raw_sessions, dict) else {}
        )
        sessions[session_key] = state
        self._kv_store.set(self._STATE_KEY, sessions)


def normalize_scene_key(value: object) -> str:
    """Normalize a model-provided scene identifier for stable comparison."""

    return " ".join(str(value or "").strip().casefold().split())


def _append_prompt_terms(value: object, terms: tuple[str, ...]) -> str:
    clean_value = str(value or "").strip().strip(",")
    existing = {
        part.strip().casefold() for part in clean_value.split(",") if part.strip()
    }
    missing = [term for term in terms if term.casefold() not in existing]
    return ", ".join(part for part in (clean_value, *missing) if part)
