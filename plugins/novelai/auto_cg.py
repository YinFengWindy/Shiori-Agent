from __future__ import annotations

from typing import Any, cast

from agent.plugins.context import PluginKVStore
from agent.prompting import PromptSectionRender
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
    """Own automatic scene-CG prompting, cooldown, and deduplication state."""

    _COOLDOWN_TURNS = 8
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

    def build_prompt_section(self, session_key: str) -> PromptSectionRender:
        """Build scene-aware CG guidance with current cooldown status."""

        state = self._get_session_state(session_key)
        turn = int(state.get("turn", 0))
        last_turn = state.get("last_success_turn")
        remaining = 0
        if isinstance(last_turn, int):
            remaining = max(0, self._COOLDOWN_TURNS + 1 - (turn - last_turn))
        cooldown_text = (
            f"自动 CG 冷却中，还需等待至少 {remaining} 个用户回合。"
            if remaining
            else "当前不在自动 CG 冷却期。"
        )
        return PromptSectionRender(
            name="novelai_auto_cg_protocol",
            content=(
                "## 自动场景 CG 协议\n"
                "你可以在角色扮演中主动生成 CG，但必须克制。只有重要地点首次出现、"
                "关系或情绪高潮、剧情转折或具有明确构图的关键动作结果，才调用 "
                "`generate_image`。普通闲聊、连续小动作和与上一张画面相近的场景不要调用。\n"
                "自动生成时必须传 `intent=scene_cg`、稳定且简短的 `scene_key`，并让 prompt "
                "使用动画 CG 式第三人称镜头：摄影机必须位于角色之外，角色本人必须清晰入镜，"
                "并用角色名或明确外貌描述角色。禁止第一人称 POV、自拍构图，以及只画角色眼中"
                "所见而不让角色入镜。prompt 只描述可见角色、动作、环境、构图、光线和氛围。"
                "单人主体优先 portrait，环境或双人场景优先 landscape。用户明确要求生图时传 "
                "`intent=user_requested`，不受自动 CG 限制。\n"
                f"当前策略状态：{cooldown_text}"
            ),
            is_static=False,
        )

    def guard(
        self,
        session_key: str,
        arguments: dict[str, Any],
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
        state = self._get_session_state(session_key)
        turn = int(state.get("turn", 0))
        last_turn = state.get("last_success_turn")
        if isinstance(last_turn, int) and turn - last_turn <= self._COOLDOWN_TURNS:
            return HookOutcome(
                decision="deny",
                reason="scene_cg_cooldown",
                extra_message="自动 CG 仍在冷却期，请继续文字回复，不要重试。",
            )
        if scene_key == str(state.get("last_scene_key") or ""):
            return HookOutcome(
                decision="deny",
                reason="scene_cg_duplicate_scene",
                extra_message="该场景已经生成过 CG，请继续文字回复，不要重复生成。",
            )
        return {
            **arguments,
            "scene_key": scene_key,
            "prompt": _append_prompt_terms(
                arguments.get("prompt"),
                _THIRD_PERSON_PROMPT_TERMS,
            ),
            "negative_prompt": _append_prompt_terms(
                arguments.get("negative_prompt"),
                _FIRST_PERSON_NEGATIVE_TERMS,
            ),
        }

    def record_success(self, session_key: str, scene_key: object) -> None:
        """Persist cooldown and deduplication state after successful generation."""

        state = self._get_session_state(session_key)
        state["last_success_turn"] = int(state.get("turn", 0))
        state["last_scene_key"] = normalize_scene_key(scene_key)
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
