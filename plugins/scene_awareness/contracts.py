from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from bus.events_lifecycle import SceneTransition
from core.integrations.novelai.models import NovelAISizePreset
from core.integrations.novelai.prompt_validation import validate_novelai_prompt

if TYPE_CHECKING:
    from agent.provider import ToolCall

SCENE_DECISION_TOOL_NAME = "submit_scene_observation"
_ALLOWED_SIZE_PRESETS = {"square", "landscape", "portrait"}
_REQUIRED_ARGUMENTS = (
    "transition",
    "should_generate",
    "scene_key",
    "prompt",
    "negative_prompt",
    "size_preset",
)

_SceneImageSizePreset = NovelAISizePreset | Literal[""]

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
                    "description": "无当前场景且出现可见场景时为 started；已有场景实质变化时为 changed；延续为 same；明确结束为 closed；仅在完全没有可见场景时为 none。",
                },
                "should_generate": {
                    "type": "boolean",
                    "description": "started 和 changed 必须为 true；closed 和 none 必须为 false。",
                },
                "scene_key": {
                    "type": "string",
                    "description": "started、changed 和 same 的稳定英文场景标识；closed 和 none 必须为空字符串。",
                },
                "prompt": {
                    "type": "string",
                    "description": "生成 CG 时的英文 NovelAI tags；不生成时必须为空字符串。",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "生成 CG 时的英文 NovelAI negative tags；不生成时必须为空字符串。",
                },
                "size_preset": {
                    "type": "string",
                    "enum": ["", "square", "landscape", "portrait"],
                    "description": "生成 CG 时选择尺寸；不生成时必须为空字符串。",
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
    recent_history: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class SceneDecision:
    """Validated scene transition and optional CG rendering request."""

    transition: SceneTransition
    scene_key: str = ""
    should_generate: bool = False
    prompt: str = ""
    negative_prompt: str = ""
    size_preset: _SceneImageSizePreset = ""


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
        tool_call_count=1,
        tool_names=tool_names,
        argument_keys=argument_keys,
        content_length=content_length,
    )


def parse_scene_decision_payload(
    payload: dict[str, Any],
    *,
    current_scene_key: str,
    tool_call_count: int = 0,
    tool_names: tuple[str, ...] = (),
    argument_keys: tuple[str, ...] = (),
    content_length: int = 0,
) -> SceneDecision:
    """Apply scene and NovelAI invariants to one schema-complete payload."""

    def fail(message: str) -> None:
        raise SceneDecisionProtocolError(
            message,
            tool_call_count=tool_call_count,
            tool_names=tool_names,
            argument_keys=argument_keys,
            content_length=content_length,
        )

    transition_text = str(payload.get("transition") or "").strip()
    if transition_text not in {"started", "same", "changed", "closed", "none"}:
        fail(f"场景观察 transition 不支持: {transition_text}")
    transition = cast(SceneTransition, transition_text)
    should_generate = payload.get("should_generate")
    if not isinstance(should_generate, bool):
        fail("场景观察缺少布尔 should_generate")
    if transition in {"started", "changed"} and not should_generate:
        fail(f"场景 {transition} 必须生成 CG")
    if transition in {"closed", "none"} and should_generate:
        fail(f"场景 {transition} 不能生成 CG")

    scene_key = str(payload.get("scene_key") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    negative_prompt = str(payload.get("negative_prompt") or "").strip()
    size_preset = str(payload.get("size_preset") or "").strip()
    has_image_parameters = any((prompt, negative_prompt, size_preset))

    if transition == "none":
        if current_scene_key:
            fail("已有场景时不能返回 none")
        if scene_key or has_image_parameters:
            fail("无场景结果不能提供场景或图像参数")
        return SceneDecision(transition=transition)
    if transition == "closed":
        if scene_key or has_image_parameters:
            fail("关闭场景结果不能提供场景或图像参数")
        return SceneDecision(transition=transition)
    if transition == "same" and not scene_key:
        scene_key = current_scene_key
    if not scene_key:
        fail("场景观察缺少 scene_key")
    if transition == "changed" and scene_key == current_scene_key:
        fail("场景 changed 必须提供新的 scene_key")
    if not should_generate:
        if has_image_parameters:
            fail("未生成 CG 的场景不能提供图像参数")
        return SceneDecision(transition=transition, scene_key=scene_key)

    if not prompt:
        fail("场景观察生成 CG 时缺少 prompt")
    if size_preset not in _ALLOWED_SIZE_PRESETS:
        fail(f"场景观察 size_preset 不支持: {size_preset}")
    try:
        validate_novelai_prompt(prompt, field_name="prompt")
        validate_novelai_prompt(negative_prompt, field_name="negative_prompt")
    except ValueError as error:
        fail(str(error))
    return SceneDecision(
        transition=transition,
        scene_key=scene_key,
        should_generate=True,
        prompt=prompt,
        negative_prompt=negative_prompt,
        size_preset=cast(_SceneImageSizePreset, size_preset),
    )
