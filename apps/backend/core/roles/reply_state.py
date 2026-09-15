"""The formal, per-turn role reply contract, independent of relationship snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class InvalidRoleReply(ValueError):
    """A final reply cannot be committed as the role's current state."""


@dataclass(frozen=True)
class RoleReply:
    """Validated dialogue and the role's own mood and first-person thought."""

    content: str
    mood: str
    thought: str


def role_mood_catalog(runtime_config: object) -> tuple[str, ...]:
    """Resolve allowed moods independently of whether illustration assets exist."""
    if not isinstance(runtime_config, dict):
        raise ValueError("角色 runtime_config 必须是字典")
    raw = runtime_config.get("mood_catalog")
    if not isinstance(raw, list) or not raw:
        bindings = runtime_config.get("mood_illustration_bindings")
        raw = list(bindings) if isinstance(bindings, dict) else []
    catalog = tuple(
        dict.fromkeys(x.strip() for x in raw if isinstance(x, str) and x.strip())
    )
    # Roles without a mood catalog still participate in the formal reply contract.
    default = str(runtime_config.get("default_mood") or "平静").strip()
    return catalog or (default,)


def role_reply_prompt(moods: tuple[str, ...]) -> str:
    """Render the same output instructions for normal and corrective generation."""
    return (
        "## Mood Output Contract\n"
        "最终回复必须是一个 JSON 对象，不要输出 JSON 之外的解释、markdown 或代码块。"
        "需要工具时正常调用工具，不要提前输出回复正文。\n"
        'JSON 结构固定为：{"content":"<角色回复正文>","mood":"<当前心情>","thought":"<当下想法>"}\n'
        f"mood 必须从角色心情目录选择：{'、'.join(moods)}。\n"
        "thought 必须是包含“我”的第一人称当下想法，1–2 句，40–70 字；"
        "content 是完整聊天正文，不受想法字数限制。"
    )


def parse_role_reply(raw: str, moods: tuple[str, ...]) -> RoleReply:
    """Validate only formal JSON; never repair truncation or inspect reasoning text."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InvalidRoleReply(f"回复 JSON 包含重复字段：{key}")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidRoleReply("角色回复必须是完整 JSON 对象") from exc
    if not isinstance(payload, dict):
        raise InvalidRoleReply("角色回复必须是 JSON 对象")
    for key in ("content", "mood", "thought"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise InvalidRoleReply(f"角色回复缺少有效 {key}")
    mood, thought = payload["mood"].strip(), payload["thought"].strip()
    if mood not in moods:
        raise InvalidRoleReply("角色回复 mood 不属于当前角色心情目录")
    if len(thought) > 100 or "我" not in thought:
        raise InvalidRoleReply("thought 必须是包含“我”的简短当下想法，不能超过 100 字")
    return RoleReply(content=payload["content"], mood=mood, thought=thought)


def reply_state_metadata(reply: RoleReply, *, updated_at: str) -> dict[str, str]:
    """Produce one session metadata update shared by all successful reply owners."""
    return {
        "current_mood": reply.mood,
        "current_mood_updated_at": updated_at,
        "current_thought": reply.thought,
        "current_thought_updated_at": updated_at,
    }
