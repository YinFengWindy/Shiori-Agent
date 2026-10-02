from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from shiori_sdk.role_events import SceneTransition

if TYPE_CHECKING:
    from agent.provider import ToolCall

SCENE_DECISION_TOOL_NAME = "submit_scene_observation"
_REQUIRED_ARGUMENTS = ("transition", "scene_key", "visual_key", "visual_description")

SCENE_DECISION_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SCENE_DECISION_TOOL_NAME,
        "description": "提交一轮角色扮演的场景观察结果。必须调用且只能调用一次。",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": list(_REQUIRED_ARGUMENTS),
            "properties": {
                "transition": {
                    "type": "string",
                    "enum": ["started", "same", "changed", "closed", "none"],
                    "description": "无当前场景且出现可见场景时为 started；场景本身切换时为 changed；同一场景延续为 same；明确结束为 closed；仅在完全没有可见场景时为 none。",
                },
                "scene_key": {
                    "type": "string",
                    "description": "持续场景的稳定英文标识。started 和 changed 提供新值；same 必须沿用 current_scene_key；closed 和 none 必须为空字符串。",
                },
                "visual_key": {
                    "type": "string",
                    "description": "本次可见定格的稳定英文标识，包含动作、姿势、位置关系、构图或光线。动作或镜头有实质变化时必须换新值；closed 和 none 必须为空字符串。",
                },
                "visual_description": {
                    "type": "string",
                    "description": "用自然语言描述已发生的可见场景事实：人物外观、动作、位置、环境及光线；不得编造后续动作。closed 和 none 为空。",
                },
            },
        },
    },
}


@dataclass(frozen=True)
class SceneDecisionInput:
    """Context used by the scene-observation model."""

    role_name: str
    role_prompt: str
    user_message: str
    assistant_reply: str = ""
    current_scene_key: str = ""
    current_visual_key: str = ""
    recent_history: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class SceneDecision:
    """Validated scene transition and provider-independent visual facts."""

    transition: SceneTransition
    scene_key: str = ""
    visual_key: str = ""
    visual_description: str = ""


class SceneDecisionProtocolError(ValueError):
    """Describes an invalid model response without retaining conversation content."""

    def __init__(
        self,
        message: str,
        *,
        tool_call_count: int = 0,
        tool_names: tuple[str, ...] = (),
        argument_keys: tuple[str, ...] = (),
        content_length: int = 0,
    ) -> None:
        super().__init__(message)
        self.tool_call_count = tool_call_count
        self.tool_names = tool_names
        self.argument_keys = argument_keys
        self.content_length = content_length


def parse_scene_decision_tool_call(
    tool_calls: list["ToolCall"],
    *,
    current_scene_key: str,
    current_visual_key: str = "",
    content_length: int,
) -> SceneDecision:
    """Validate the required scene-observation tool call and its arguments."""

    tool_names = tuple(str(call.name or "") for call in tool_calls)
    if len(tool_calls) != 1:
        raise SceneDecisionProtocolError(
            "场景观察必须调用一次提交工具",
            tool_call_count=len(tool_calls),
            tool_names=tool_names,
            content_length=content_length,
        )
    tool_call = tool_calls[0]
    if tool_call.name != SCENE_DECISION_TOOL_NAME:
        raise SceneDecisionProtocolError(
            "场景观察调用了错误的提交工具",
            tool_call_count=1,
            tool_names=tool_names,
            content_length=content_length,
        )
    arguments = tool_call.arguments
    if not isinstance(arguments, dict):
        raise SceneDecisionProtocolError(
            "场景观察提交工具参数必须是对象",
            tool_call_count=1,
            tool_names=tool_names,
            content_length=content_length,
        )
    argument_keys = tuple(sorted(str(key) for key in arguments))
    missing = [key for key in _REQUIRED_ARGUMENTS if key not in arguments]
    if missing:
        raise SceneDecisionProtocolError(
            f"场景观察提交工具缺少参数: {', '.join(missing)}",
            tool_call_count=1,
            tool_names=tool_names,
            argument_keys=argument_keys,
            content_length=content_length,
        )
    return parse_scene_decision_payload(
        arguments,
        current_scene_key=current_scene_key,
        current_visual_key=current_visual_key,
        tool_call_count=1,
        tool_names=tool_names,
        argument_keys=argument_keys,
        content_length=content_length,
    )


def parse_scene_decision_payload(
    payload: dict[str, Any],
    *,
    current_scene_key: str,
    current_visual_key: str = "",
    tool_call_count: int = 0,
    tool_names: tuple[str, ...] = (),
    argument_keys: tuple[str, ...] = (),
    content_length: int = 0,
) -> SceneDecision:
    """Apply neutral scene invariants to one schema-complete payload."""

    def fail(message: str) -> None:
        raise SceneDecisionProtocolError(
            message,
            tool_call_count=tool_call_count,
            tool_names=tool_names,
            argument_keys=argument_keys,
            content_length=content_length,
        )

    if any(not isinstance(payload.get(key), str) for key in _REQUIRED_ARGUMENTS):
        fail("场景观察参数必须是字符串")
    transition_text = str(payload.get("transition") or "").strip()
    if transition_text not in {"started", "same", "changed", "closed", "none"}:
        fail(f"场景观察 transition 不支持: {transition_text}")
    transition = cast(SceneTransition, transition_text)
    scene_key = str(payload.get("scene_key") or "").strip()
    visual_key = str(payload.get("visual_key") or "").strip()
    visual_description = str(payload.get("visual_description") or "").strip()
    if set(payload) - set(_REQUIRED_ARGUMENTS):
        fail("场景观察包含未知参数")

    if transition == "none":
        if current_scene_key:
            fail("已有场景时不能返回 none")
        if scene_key or visual_key or visual_description:
            fail("无场景结果不能提供场景或视觉描述")
        return SceneDecision(transition=transition)
    if transition == "closed":
        if scene_key or visual_key or visual_description:
            fail("关闭场景结果不能提供场景或视觉描述")
        return SceneDecision(transition=transition)
    if transition == "same" and not scene_key:
        scene_key = current_scene_key
    if not scene_key:
        fail("场景观察缺少 scene_key")
    if transition == "changed" and scene_key == current_scene_key:
        fail("场景 changed 必须提供新的 scene_key")
    if transition == "same" and scene_key != current_scene_key:
        fail("场景 same 必须沿用 current_scene_key")
    if transition == "same" and not visual_key:
        visual_key = current_visual_key
    if not visual_key:
        fail("场景观察缺少 visual_key")
    if not visual_description:
        fail("可见场景缺少 visual_description")
    return SceneDecision(
        transition=transition,
        scene_key=scene_key,
        visual_key=visual_key,
        visual_description=visual_description,
    )
