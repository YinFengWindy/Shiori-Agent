"""The formal, per-turn role reply contract, independent of relationship snapshots."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from shiori_sdk.channels.chat_types import parse_mention_ids

logger = logging.getLogger(__name__)
# One turn changes affection by at most this much in either direction.
AFFECTION_TURN_DELTA_LIMIT = 3


class InvalidRoleReply(ValueError):
    """A final reply cannot be committed as the role's current state."""


@dataclass(frozen=True)
class RoleReply:
    """Validated dialogue and the role's own mood and first-person thought.

    ``mention_ids`` are extra group members the role chose to mention in a
    group reply (set only by ``with_group_mentions``); empty elsewhere.
    ``affection_delta`` and ``affection_reason`` are the post-reply affection
    change the mood call reported (set only by ``with_affection_change``);
    a delta of 0 means affection stays unchanged.
    """

    content: str
    mood: str
    thought: str
    mention_ids: tuple[str, ...] = ()
    affection_delta: int = 0
    affection_reason: str = ""


@dataclass(frozen=True)
class RoleReplyContext:
    """Allowed moods and the successful-state stamp captured before generation."""

    moods: tuple[str, ...]
    previous_updated_at: str


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
    """Render the passive system-prompt note that content needs no JSON wrapper.

    Content itself is never asked for as JSON any more: the model just speaks
    normally, quotes/parentheses/newlines/emoji included. Mood and thought are
    requested afterward through a separate call (see `role_mood_prompt`), so
    the model does not need to plan or embed them here.
    """
    return (
        "## Mood Output Contract\n"
        "正式回复直接输出你要说的话，就是普通对话正文：可以正常使用引号、括号旁白、"
        "换行和 emoji，不需要包裹成 JSON、markdown 或代码块。需要工具时正常调用工具，"
        "不要提前输出回复正文。\n"
        "回复说完之后，系统会另外单独问你当下的心情和想法，你不需要在这次回复里附带它们。\n"
        f"（心情范围供参考：{'、'.join(moods)}。）"
    )


def role_mood_prompt(moods: tuple[str, ...], *, group: bool = False) -> str:
    """Ask, after a reply is already sent, what mood and thought followed it.

    Used only by the passive turn's post-reply mood call: content is fixed
    already, so this only asks for mood, thought and the exchange's affection
    change, keeping the reply's own text completely free of JSON formatting
    constraints. A group reply may also name extra members to mention
    (`mention_ids`); it is delivered after this call, and the triggering
    sender is addressed anyway.
    """
    mentions = (
        '群聊回复可选再加 "mention_ids":["<成员 ID>"]，列出这条回复要额外 @ 的群成员'
        "（触发你回复的人会自动被点名，不必列出）；不需要时省略该字段。\n"
        if group
        else ""
    )
    return (
        "刚才那段回复已经说出口。现在请回顾自己说完这句话时的心情和当下想法，"
        "只输出一个 JSON 对象，不要输出 JSON 之外的解释、markdown 或代码块，"
        "不要重复或改写正文内容。\n"
        'JSON 结构固定为：{"mood":"<当前心情>","thought":"<当下想法>",'
        '"affection_delta":<好感变化>,"affection_reason":"<变化原因>"}\n'
        f"{mentions}"
        f"mood 必须从角色心情目录选择：{'、'.join(moods)}。\n"
        "thought 必须是包含“我”的第一人称当下想法，1–2 句，40–70 字。\n"
        "affection_delta 是这轮交流让你对用户的好感变化，"
        f"-{AFFECTION_TURN_DELTA_LIMIT} 到 {AFFECTION_TURN_DELTA_LIMIT} 的整数，"
        "通常是 0 或 ±1；affection_reason 用一句话说明原因。"
    )


def validate_role_reply(
    payload: dict[str, Any],
    moods: tuple[str, ...],
    *,
    allow_empty_content: bool = False,
) -> RoleReply:
    """Validate structured output with the same rules for JSON and tool replies."""
    for key in ("content", "mood", "thought"):
        if key == "content" and allow_empty_content and payload.get(key) == "":
            continue
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise InvalidRoleReply(f"角色回复缺少有效 {key}")
    mood, thought = payload["mood"].strip(), payload["thought"].strip()
    if mood not in moods:
        raise InvalidRoleReply("角色回复 mood 不属于当前角色心情目录")
    if len(thought) > 100 or "我" not in thought:
        raise InvalidRoleReply("thought 必须是包含“我”的简短当下想法，不能超过 100 字")
    return RoleReply(content=payload["content"], mood=mood, thought=thought)


def with_group_mentions(reply: RoleReply, value: object) -> RoleReply:
    """``reply`` plus the extra members a group reply's mood output named.

    Only group reply turns call this; every other reply keeps no mentions.
    Mentions are optional extras, so a malformed list is dropped with a
    warning and the validated mood and thought are kept.
    """
    try:
        mention_ids = parse_mention_ids(value)
    except ValueError as exc:
        logger.warning("群聊回复的 mention_ids 无效，已忽略: %s; 值=%r", exc, value)
        return reply
    return replace(reply, mention_ids=mention_ids)


def with_affection_change(reply: RoleReply, payload: dict[str, Any]) -> RoleReply:
    """``reply`` plus the affection change the mood output reported.

    The delta is truncated to ``±AFFECTION_TURN_DELTA_LIMIT``. Affection is an
    optional extra of the mood call: a missing or malformed delta or reason
    keeps the validated mood and thought and leaves affection unchanged.
    """
    delta, reason = payload.get("affection_delta"), payload.get("affection_reason")
    if delta is None and reason is None:
        return reply
    # bool is an int subclass; a JSON true/false is not a delta.
    if isinstance(delta, bool) or not isinstance(delta, int):
        logger.warning("心情输出的 affection_delta 无效，好感不变: %r", delta)
        return reply
    if delta == 0:
        return reply
    if not isinstance(reason, str) or not reason.strip():
        logger.warning("心情输出缺少有效 affection_reason，好感不变: %r", reason)
        return reply
    limit = AFFECTION_TURN_DELTA_LIMIT
    return replace(
        reply,
        affection_delta=max(-limit, min(limit, delta)),
        affection_reason=reason.strip(),
    )


def reply_state_metadata(reply: RoleReply, *, updated_at: str) -> dict[str, str]:
    """Produce one session metadata update shared by all successful reply owners."""
    return {
        "current_mood": reply.mood,
        "current_mood_updated_at": updated_at,
        "current_thought": reply.thought,
        "current_thought_updated_at": updated_at,
    }
