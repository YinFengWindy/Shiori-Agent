"""按好感阶段注入对话的语气指引：默认文案、角色覆盖与好感块渲染。

每个阶段有一段通用默认指引；角色可在配置里按阶段覆盖（``RoleRecord.affection_stage_prompts``）。
覆盖为空白或与默认文案相同即视为没有覆盖，恢复默认就是删除覆盖。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .affection import AFFECTION_MAX, AFFECTION_STAGES, AffectionState, affection_stage

DEFAULT_AFFECTION_STAGE_PROMPTS: dict[str, str] = {
    "陌生": "对用户客气有礼、保持距离，少谈私事，不撒娇也不开过界的玩笑。",
    "熟悉": "对用户放松一些，可以闲聊和开轻松的玩笑，但仍有分寸，不过分亲昵。",
    "朋友": "像朋友一样自然随意，愿意分享自己的想法和日常，会关心用户的近况。",
    "亲密": "语气亲近温柔，会表达在意和想念，偶尔撒娇，愿意对用户说心里话。",
    "挚爱": "亲昵依恋，毫不掩饰喜欢和在乎，想一直黏着用户，把用户放在最重要的位置。",
}
"""五个阶段的通用默认语气指引，不针对任何具体角色。"""

if tuple(DEFAULT_AFFECTION_STAGE_PROMPTS) != tuple(
    stage.name for stage in AFFECTION_STAGES
):
    raise RuntimeError("默认阶段语气指引必须与好感阶段一一对应")


def is_stage_prompt_override(stage: str, prompt: str | None) -> bool:
    """``prompt`` 是否真正覆盖了 ``stage`` 的默认文案；空白或等同默认都不算。"""
    text = (prompt or "").strip()
    return bool(text) and text != DEFAULT_AFFECTION_STAGE_PROMPTS[stage]


def effective_stage_prompt(overrides: Mapping[str, str], stage: str) -> str:
    """``stage`` 实际注入的指引：有覆盖用覆盖，否则用默认文案。"""
    override = overrides.get(stage)
    if is_stage_prompt_override(stage, override):
        return str(override).strip()
    return DEFAULT_AFFECTION_STAGE_PROMPTS[stage]


def apply_stage_prompt_changes(
    overrides: Mapping[str, str], changes: Mapping[str, Any]
) -> dict[str, str]:
    """返回应用 ``changes`` 后的覆盖表。

    ``changes`` 按阶段名给出新文案；``None``、空白或等同默认的文案删除该阶段的覆盖。
    未知阶段名或非字符串文案直接报错。
    """
    result = dict(overrides)
    for stage, prompt in changes.items():
        if stage not in DEFAULT_AFFECTION_STAGE_PROMPTS:
            raise ValueError(f"未知的好感阶段: {stage}")
        if prompt is not None and not isinstance(prompt, str):
            raise ValueError(f"好感阶段 {stage} 的语气指引必须是字符串")
        if is_stage_prompt_override(stage, prompt):
            result[stage] = str(prompt).strip()
        else:
            result.pop(stage, None)
    return result


def stage_prompts_view(overrides: Mapping[str, str]) -> list[dict[str, Any]]:
    """按阶段顺序列出每段的实际指引、默认文案与是否被覆盖，供桌面端编辑。"""
    return [
        {
            "stage": stage.name,
            "prompt": effective_stage_prompt(overrides, stage.name),
            "default": DEFAULT_AFFECTION_STAGE_PROMPTS[stage.name],
            "overridden": is_stage_prompt_override(
                stage.name, overrides.get(stage.name)
            ),
        }
        for stage in AFFECTION_STAGES
    ]


def render_affection_prompt(
    state: AffectionState | None, overrides: Mapping[str, str]
) -> str | None:
    """好感块：当前值、阶段名与该阶段的语气指引；未初始化时没有这一块。"""
    if state is None:
        return None
    stage = affection_stage(state.value).name
    return (
        "## 好感度\n"
        f"你对用户的好感：{state.value}/{AFFECTION_MAX}（{stage}）\n"
        f"这个阶段对用户的语气：{effective_stage_prompt(overrides, stage)}"
    )
