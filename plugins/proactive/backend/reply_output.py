"""Shared proactive tool-output validation and one correction per tick."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from .results import InvalidRoleReply, RoleReply
from .context import AgentTickContext
from .outbound_text import normalize_outbound_text
from .session_key import role_id_from_session_key
from shiori_sdk.core.proactive_host import ProactiveHost

logger = logging.getLogger(__name__)


def reply_properties(moods: tuple[str, ...]) -> dict[str, Any]:
    """Describe formal state on message_push without changing final tool decisions."""
    return {
        "mood": {"type": "string", **({"enum": list(moods)} if moods else {})},
        "thought": {
            "type": "string",
            "description": "包含“我”的第一人称当下想法，1–2句，约40–70字；不要放入message正文",
        },
    }


def reply_schemas(
    schemas: list[dict], ctx: AgentTickContext, host: ProactiveHost
) -> list[dict]:
    """Bind the current role catalog to message_push, leaving other tools intact.

    Inside the tick's natural plan the draft carries a message list instead of
    one message.
    """
    if ctx.reply_context is None:
        raise InvalidRoleReply("主动回复缺少生成起点角色状态")
    result = deepcopy(schemas)
    for schema in result:
        function = schema["function"]
        if function["name"] != "message_push":
            continue
        parameters = function["parameters"]
        parameters["properties"].update(reply_properties(ctx.reply_context.moods))
        if host.natural_reply_active():
            function["description"] = function["description"].replace(
                "向用户发送一条消息", "提交本轮要发送的消息列表"
            )
            properties = parameters["properties"]
            properties.pop("message", None)
            properties.pop("content", None)
            properties.update(host.natural_reply_properties())
            parameters["required"] = [
                name
                for name in parameters.get("required", [])
                if name not in {"message", "content"}
            ] + ["messages"]
        parameters["required"] = list(
            dict.fromkeys([*parameters.get("required", []), "mood", "thought"])
        )
    return result


def parse_push_reply(
    args: dict, ctx: AgentTickContext, host: ProactiveHost
) -> RoleReply:
    """Validate tool fields before any draft or delivery side effect occurs."""
    if ctx.reply_context is None:
        raise InvalidRoleReply("主动回复缺少生成起点角色状态")
    if host.natural_reply_active():
        accepted = host.natural_reply_messages()
        if accepted is None or args.get("messages") != list(accepted):
            raise InvalidRoleReply("主动自然回复尚未通过消息列表校验")
        content = "\n\n".join(accepted)
    else:
        content = args.get("message", args.get("content", ""))
        if isinstance(content, str):
            content = normalize_outbound_text(content).strip()
    media = args.get("media")
    has_media = bool(
        isinstance(args.get("image"), str)
        and args["image"].strip()
        or isinstance(media, str)
        and media.strip()
        or isinstance(media, list)
        and any(isinstance(item, str) and item.strip() for item in media)
    )
    try:
        validated = host.validate_reply(
            role_id_from_session_key(ctx.session_key),
            content=str(content or ""),
            mood=str(args.get("mood") or ""),
            thought=str(args.get("thought") or ""),
            allow_empty_content=has_media,
        )
    except ValueError as exc:
        raise InvalidRoleReply(str(exc)) from exc
    return RoleReply(
        content=validated.content, mood=validated.mood, thought=validated.thought
    )


async def correct_push_call(
    call: dict,
    *,
    ctx: AgentTickContext,
    messages: list[dict],
    schemas: list[dict],
    llm_fn: Callable[..., Awaitable[dict | None]],
    remaining_steps: int,
    host: ProactiveHost,
) -> dict:
    """Repair only invalid formal fields once, without executing or replaying tools."""
    if call.get("name") != "message_push":
        return call
    try:
        parse_push_reply(call.get("input", {}), ctx, host)
        return call
    except InvalidRoleReply as exc:
        # Natural content has one shared completion-only correction. Never open
        # another draft/business-tool request to repair its role-state fields.
        if (
            host.natural_reply_active()
            or ctx.reply_format_corrections
            or remaining_steps <= 0
        ):
            raise
        logger.warning("Invalid proactive role reply: %s", exc)
        ctx.reply_format_corrections += 1
        ctx.steps_taken += 1
        correction_messages = [
            *messages,
            {
                "role": "user",
                "content": (
                    "message_push 参数校验失败："
                    + str(exc)
                    + "。只允许纠正一次。请调用 message_push 补全合法 mood/thought；"
                    "保留原 message、媒体、evidence 和目标参数，不要执行其他工具。原参数："
                    + json.dumps(call.get("input", {}), ensure_ascii=False)
                ),
            },
        ]
    corrected = await llm_fn(
        correction_messages,
        [s for s in schemas if s["function"]["name"] == "message_push"],
        {"type": "function", "function": {"name": "message_push"}},
    )
    if corrected is None or corrected.get("name") != "message_push":
        raise InvalidRoleReply("主动回复格式纠正未返回 message_push")
    original_args = call.get("input", {})
    corrected_args = corrected.get("input", {})
    # A format correction cannot alter the intended payload or introduce side effects.
    for key in set(original_args) | set(corrected_args):
        if key not in {"mood", "thought"} and original_args.get(
            key
        ) != corrected_args.get(key):
            raise InvalidRoleReply("主动回复格式纠正改写了消息或投递参数")
    parse_push_reply(corrected_args, ctx, host)
    return corrected
