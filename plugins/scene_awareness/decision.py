from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from agent.llm_json import load_json_object_loose
from bus.events_lifecycle import SceneTransition
from core.integrations.novelai.models import NovelAISizePreset
from core.integrations.novelai.prompt_validation import validate_novelai_prompt

if TYPE_CHECKING:
    from infra.providers.llm_provider import LLMProvider

_ALLOWED_SIZE_PRESETS = {"square", "landscape", "portrait"}


@dataclass(frozen=True)
class SceneDecisionInput:
    """Context used by the scene-awareness decision model."""

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
    size_preset: NovelAISizePreset = "landscape"


async def decide_scene(
    provider: "LLMProvider",
    *,
    model: str,
    decision_input: SceneDecisionInput,
) -> SceneDecision:
    """Classify one completed role turn and return a validated scene decision."""

    clean_model = model.strip()
    if not clean_model:
        raise ValueError("场景观察缺少 light_model")
    response = await provider.chat(
        messages=[{"role": "user", "content": _build_decision_prompt(decision_input)}],
        tools=[],
        model=clean_model,
        max_tokens=600,
        tool_choice="none",
        disable_thinking=True,
    )
    payload = load_json_object_loose((response.content or "").strip())
    if payload is None:
        raise ValueError("场景观察未返回合法 JSON")
    return _parse_decision(payload, current_scene_key=decision_input.current_scene_key)


def _build_decision_prompt(decision_input: SceneDecisionInput) -> str:
    context = {
        "role_name": decision_input.role_name,
        "role_prompt": decision_input.role_prompt[:4000],
        "current_scene_key": decision_input.current_scene_key,
        "recent_history": list(decision_input.recent_history[-6:]),
        "user_message": decision_input.user_message,
        "assistant_reply": decision_input.assistant_reply,
    }
    return (
        "你是角色扮演场景观察器。根据刚完成的一轮对话识别可见场景状态，并判断是否值得补发 CG。\n"
        "transition 只能是 started、same、changed、closed、none。没有 current_scene_key 且形成了明确可见场景时为 started；"
        "已有场景且地点、姿势、位置关系、人物关系或构图发生实质变化时为 changed；"
        "已有场景且没有实质变化时为 same；告别、睡觉、离场或场景明确结束时为 closed；"
        "没有 current_scene_key 且本轮没有形成任何明确可见场景时为 none。\n"
        "started 和 changed 必须返回 should_generate=true，并提供新的稳定英文 scene_key 及完整 CG 参数。"
        "same 只有在形成清晰、值得额外定格且尚未覆盖的画面时才返回 should_generate=true；"
        "closed 和 none 必须返回 should_generate=false。none 不得提供 scene_key、prompt、negative_prompt 或 size_preset。"
        "普通闲聊、技术讨论以及用户明确要求生图但未形成可见场景的回合应返回 none，不额外补图。\n"
        "生成 CG 时，prompt 和 negative_prompt 必须是逗号分隔的英文 NovelAI tags，禁止中文和自然语言句子。"
        "prompt 只描述最新回合中明确可见的角色、动作、环境、构图、光线和氛围；"
        "size_preset 只能是 square、landscape、portrait。只输出 JSON，不要解释。\n\n"
        f"context:\n{json.dumps(context, ensure_ascii=False)}"
    )


def _parse_decision(
    payload: dict[str, object],
    *,
    current_scene_key: str,
) -> SceneDecision:
    transition_text = str(payload.get("transition") or "").strip()
    if transition_text not in {"started", "same", "changed", "closed", "none"}:
        raise ValueError(f"场景观察 transition 不支持: {transition_text}")
    transition = cast(SceneTransition, transition_text)
    should_generate = payload.get("should_generate")
    if not isinstance(should_generate, bool):
        raise ValueError("场景观察缺少布尔 should_generate")
    if transition in {"started", "changed"} and not should_generate:
        raise ValueError(f"场景 {transition} 必须生成 CG")
    if transition in {"closed", "none"} and should_generate:
        raise ValueError(f"场景 {transition} 不能生成 CG")

    scene_key = str(payload.get("scene_key") or "").strip()
    if transition == "none":
        image_fields = ("scene_key", "prompt", "negative_prompt", "size_preset")
        if any(str(payload.get(field) or "").strip() for field in image_fields):
            raise ValueError("无场景结果不能提供场景或图像参数")
        if current_scene_key:
            raise ValueError("已有场景时不能返回 none")
        return SceneDecision(transition=transition)
    if transition == "same" and not scene_key:
        scene_key = current_scene_key
    if transition == "closed":
        return SceneDecision(transition=transition)
    if not scene_key:
        raise ValueError("场景观察缺少 scene_key")
    if transition == "changed" and scene_key == current_scene_key:
        raise ValueError("场景 changed 必须提供新的 scene_key")
    if not should_generate:
        return SceneDecision(transition=transition, scene_key=scene_key)

    prompt = str(payload.get("prompt") or "").strip()
    negative_prompt = str(payload.get("negative_prompt") or "").strip()
    size_preset = str(payload.get("size_preset") or "").strip()
    if not prompt:
        raise ValueError("场景观察生成 CG 时缺少 prompt")
    if size_preset not in _ALLOWED_SIZE_PRESETS:
        raise ValueError(f"场景观察 size_preset 不支持: {size_preset}")
    validate_novelai_prompt(prompt, field_name="prompt")
    validate_novelai_prompt(negative_prompt, field_name="negative_prompt")
    return SceneDecision(
        transition=transition,
        scene_key=scene_key,
        should_generate=True,
        prompt=prompt,
        negative_prompt=negative_prompt,
        size_preset=cast(NovelAISizePreset, size_preset),
    )
