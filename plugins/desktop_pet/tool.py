from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agent.tools.base import Tool
from bus.events_lifecycle import DesktopPetActionRequested
from core.roles.store import RoleStore

_COOLDOWN_SECONDS = 3.0
_POSITION_TARGETS = frozenset(
    {"top_left", "top_right", "center", "bottom_left", "bottom_right"}
)
_MOVE_ANIMATIONS = frozenset({"", "idle", "run"})


class DesktopPetActionTool(Tool):
    """Validates one role-scoped desktop-pet command before publishing it."""

    name = "pet_action"
    description = (
        "操控当前绑定的桌宠。支持移动到受限位置，或播放当前桌宠包声明的语义动作。"
        "仅桌面端会话可用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["move", "play"],
                "description": "命令类型：move 移动位置，play 播放桌宠包动作。",
            },
            "target": {
                "type": "string",
                "enum": ["top_left", "top_right", "center", "bottom_left", "bottom_right"],
                "description": "move 的语义位置目标。",
            },
            "name": {
                "type": "string",
                "description": "play 的桌宠包动作名称。",
            },
            "animation": {
                "type": "string",
                "enum": ["", "idle", "run"],
                "description": "move 的移动表现。",
            },
        },
        "required": ["action"],
    }

    def __init__(
        self,
        *,
        role_store: RoleStore,
        event_bus: Any,
        tool_registry: Any,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._role_store = role_store
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._clock = clock
        self._last_action_at: dict[str, float] = {}
        self._last_turn_key: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(
        self,
        *,
        action: str,
        target: str = "",
        name: str = "",
        animation: str = "",
        **_: Any,
    ) -> str:
        context = self._tool_registry.get_context()
        channel = str(context.get("channel") or "").strip()
        role_id = str(context.get("role_id") or "").strip()
        session_key = str(context.get("session_key") or "").strip()
        if channel != "desktop":
            return _rejected("unsupported_channel")
        if not role_id or not session_key:
            return _rejected("missing_role_context")

        role = self._role_store.get_role(role_id)
        if role is None or not role.desktop_pet_enabled:
            return _rejected("pet_not_enabled")
        package = next(
            (item for item in role.pet_packages if item.id == role.selected_pet_package_id),
            None,
        )
        if package is None:
            return _rejected("pet_not_bound_to_role")

        clean_action = action.strip()
        clean_target = target.strip()
        clean_name = name.strip()
        clean_animation = animation.strip()
        if clean_action == "move":
            if clean_target not in _POSITION_TARGETS:
                return _rejected("invalid_target")
            if clean_animation not in _MOVE_ANIMATIONS:
                return _rejected("invalid_animation")
        elif clean_action == "play":
            if not clean_name or clean_name not in package.actions:
                return _rejected("action_not_supported")
        else:
            return _rejected("invalid_action")

        lock = self._locks.setdefault(role_id, asyncio.Lock())
        async with lock:
            now = self._clock()
            last_action = self._last_action_at.get(role_id)
            if last_action is not None and now - last_action < _COOLDOWN_SECONDS:
                return _rejected("rate_limited")
            turn_key = f"{session_key}:{context.get('current_timestamp', '')}"
            if self._last_turn_key.get(role_id) == turn_key:
                return _rejected("turn_action_limit")

            action_id = f"pet-action-{uuid4().hex}"
            request = await self._event_bus.emit(
                DesktopPetActionRequested(
                    action_id=action_id,
                    role_id=role_id,
                    session_key=session_key,
                    channel=channel,
                    kind=clean_action,
                    name=clean_name,
                    target=clean_target,
                    animation=clean_animation,
                    state=package.actions.get(clean_name, ""),
                )
            )
            if request.error or not request.dispatched:
                return _rejected(request.error or "desktop_bridge_unavailable", action_id=action_id)
            self._last_action_at[role_id] = now
            self._last_turn_key[role_id] = turn_key
            return json.dumps(
                {
                    "accepted": True,
                    "action_id": action_id,
                    "action": clean_action,
                    "name": clean_name,
                    "target": clean_target,
                    "channel": channel,
                },
                ensure_ascii=False,
            )


def _rejected(reason: str, *, action_id: str = "") -> str:
    return json.dumps(
        {"accepted": False, "reason": reason, **({"action_id": action_id} if action_id else {})},
        ensure_ascii=False,
    )
