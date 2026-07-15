from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from agent.llm_json import load_json_object_loose
from core.integrations.novelai.models import NovelAISizePreset
from core.integrations.novelai.prompt_validation import validate_novelai_prompt

if TYPE_CHECKING:
    from infra.providers.llm_provider import LLMProvider

_ALLOWED_SIZE_PRESETS = {"square", "landscape", "portrait"}
SceneTransition = Literal["same", "changed", "closed"]


@dataclass(frozen=True)
class SceneCgDecisionInput:
    """Context used by the asynchronous scene-CG decision model."""

    role_name: str
    role_prompt: str
    user_message: str
    assistant_reply: str = ""
    recent_history: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class SceneCgDecision:
    """Validated structured decision returned by the scene-CG classifier."""

    should_generate: bool
    scene_transition: SceneTransition = "same"
    scene_key: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    size_preset: NovelAISizePreset = "landscape"


async def decide_scene_cg(
    provider: "LLMProvider",
    *,
    model: str,
    decision_input: SceneCgDecisionInput,
) -> SceneCgDecision:
    """Classify one completed role turn and return a validated CG decision."""

    clean_model = model.strip()
    if not clean_model:
        raise ValueError("自动场景 CG 缺少 light_model")
    response = await provider.chat(
        messages=[
            {
                "role": "user",
                "content": _build_decision_prompt(decision_input),
            }
        ],
        tools=[],
        model=clean_model,
        max_tokens=600,
        tool_choice="none",
        disable_thinking=True,
    )
    payload = load_json_object_loose((response.content or "").strip())
    if payload is None:
        raise ValueError("自动场景 CG 判定未返回合法 JSON")
    return _parse_decision(payload)


def _build_decision_prompt(decision_input: SceneCgDecisionInput) -> str:
    context = {
        "role_name": decision_input.role_name,
        "role_prompt": decision_input.role_prompt[:4000],
        "recent_history": list(decision_input.recent_history[-6:]),
        "user_message": decision_input.user_message,
        "assistant_reply": decision_input.assistant_reply,
    }
    return (
        "你是角色扮演场景 CG 判定器。根据刚完成的一轮对话，判断是否值得主动补发一张 CG。\n"
        "同时判断当前回合与上一段场景的关系：scene_transition 只能是 same、changed、closed。"
        "same 表示仍在同一场景，changed 表示明确转入新场景，closed 表示告别、睡觉或场景结束。\n"
        "只有以下情况返回 should_generate=true：重要地点首次清晰出现、关系或情绪高潮、"
        "剧情转折、或具有明确构图的关键动作结果。普通闲聊、轻微动作、重复场景、技术讨论、"
        "以及用户明确要求生图的回合都返回 false。\n"
        "命中时，scene_key 使用简短稳定的英文场景标识；prompt 和 negative_prompt 必须是"
        "逗号分隔的英文 NovelAI tags，禁止中文和自然语言句子。prompt 只描述可见角色、"
        "动作、环境、构图、光线和氛围，不要写对白、心理或不可见信息。"
        "size_preset 只能是 square、landscape、portrait。\n"
        "只输出 JSON，不要解释。未命中格式："
        '{"should_generate":false,"scene_transition":"same"}。命中格式：'
        '{"should_generate":true,"scene_transition":"same","scene_key":"...","prompt":"...",'
        '"negative_prompt":"...","size_preset":"portrait"}。\n\n'
        f"context:\n{json.dumps(context, ensure_ascii=False)}"
    )


def _parse_decision(payload: dict[str, object]) -> SceneCgDecision:
    should_generate = payload.get("should_generate")
    if not isinstance(should_generate, bool):
        raise ValueError("自动场景 CG 判定缺少布尔 should_generate")
    scene_transition_text = str(payload.get("scene_transition") or "same").strip()
    if scene_transition_text not in {"same", "changed", "closed"}:
        raise ValueError(f"自动场景 CG scene_transition 不支持: {scene_transition_text}")
    scene_transition = cast(SceneTransition, scene_transition_text)
    if not should_generate:
        return SceneCgDecision(
            should_generate=False,
            scene_transition=scene_transition,
        )

    scene_key = str(payload.get("scene_key") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    negative_prompt = str(payload.get("negative_prompt") or "").strip()
    size_preset = str(payload.get("size_preset") or "").strip()
    if not scene_key:
        raise ValueError("自动场景 CG 判定缺少 scene_key")
    if not prompt:
        raise ValueError("自动场景 CG 判定缺少 prompt")
    if size_preset not in _ALLOWED_SIZE_PRESETS:
        raise ValueError(f"自动场景 CG size_preset 不支持: {size_preset}")
    validate_novelai_prompt(prompt, field_name="prompt")
    validate_novelai_prompt(negative_prompt, field_name="negative_prompt")
    return SceneCgDecision(
        should_generate=True,
        scene_transition=scene_transition,
        scene_key=scene_key,
        prompt=prompt,
        negative_prompt=negative_prompt,
        size_preset=size_preset,  # type: ignore[arg-type]
    )
