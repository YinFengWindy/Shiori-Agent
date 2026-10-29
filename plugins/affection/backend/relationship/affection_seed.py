"""在 SELF 就绪后由对话模型判断角色的初始好感度。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shiori_sdk.core.affection_host import AffectionHost, AffectionRole
from shiori_sdk.json import load_json_object_loose

from .affection import AFFECTION_MAX, AFFECTION_MIN, AFFECTION_STAGES
from .affection_service import RoleAffectionService
from .interaction import render_recent_messages

_AFFECTION_SEED_SYSTEM = (
    "你在判断一个角色此刻对用户的初始好感度。只输出一个 JSON 对象，不要输出其他内容。"
)

_AFFECTION_SEED_PROMPT = """\
请根据以下资料，判断角色此刻对用户的初始好感度。

好感度是 {minimum} 到 {maximum} 的整数，分为以下阶段：
{stages}

判断规则：
- 以角色设定和 SELF.md 中 `## 我们的关系` 描述的关系基调为主要依据
- 设定里本来就亲密的关系可以从较高阶段开始；没有依据时不要虚构亲密
- 负值表示角色对用户抱有反感或敌意，例如设定中与用户敌对、有过节；0 附近是没有特别好恶的陌生人；没有依据时不要虚构敌意
- 如有长期记忆或近期互动，它们是真实发生过的关系证据，应一并考虑；为空时只按设定判断

只输出 JSON：{{"value": 整数, "reason": "一句话说明为什么是这个值"}}

角色名称：
{role_name}

角色简介：
{role_description}

角色定义：
{role_prompt}

SELF.md：
{self_text}

MEMORY.md：
{memory_text}

近期互动：
{recent_messages}
"""


@dataclass(frozen=True)
class AffectionSeed:
    """模型给出的初始好感度与原因。"""

    value: int
    reason: str


def parse_affection_seed(text: str) -> AffectionSeed:
    """Parses ``{"value": int, "reason": str}``; anything else is an error, never a default."""
    payload = load_json_object_loose(text.strip())
    if payload is None:
        raise ValueError("好感度初始化必须返回 JSON 对象")
    value = payload.get("value")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("好感度初始化的 value 必须是整数")
    if not AFFECTION_MIN <= value <= AFFECTION_MAX:
        raise ValueError(f"好感度初始化的 value 超出范围: {value}")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("好感度初始化缺少原因")
    return AffectionSeed(value=value, reason=reason.strip())


class RoleAffectionInitializer:
    """Initializes affection once per role; callers hold the role turn lock."""

    def __init__(self, sources: AffectionHost, affection: RoleAffectionService) -> None:
        self._sources = sources
        self._affection = affection

    async def ensure_initialized(
        self, role_id: str, *, now: datetime | None = None
    ) -> None:
        """Seeds affection when missing; failures propagate and leave it uninitialized."""
        if self._affection.read_state(role_id) is not None:
            return
        role = self._sources.get_role(role_id)
        if role is None:
            raise ValueError(f"role not found: {role_id}")
        seed = parse_affection_seed(
            await self._sources.complete(
                role_id,
                [
                    {"role": "system", "content": _AFFECTION_SEED_SYSTEM},
                    {"role": "user", "content": self._prompt(role)},
                ],
                max_tokens=None,
            )
        )
        self._affection.initialize(
            role_id, value=seed.value, reason=seed.reason, now=now
        )

    def _prompt(self, role: AffectionRole) -> str:
        role_id = role.id
        session = self._sources.get_session(self._sources.role_session_key(role_id))
        recent = self._sources.recent_user_messages(role_id, list(session.messages))
        memory = self._sources.read_long_term(role_id)
        # An untouched template is no evidence; render it as empty so the
        # "judge by profile only" rule applies to brand-new roles.
        if self._sources.memory_is_template(memory):
            memory = ""
        return _AFFECTION_SEED_PROMPT.format(
            minimum=AFFECTION_MIN,
            maximum=AFFECTION_MAX,
            stages="\n".join(
                f"- {stage.name}：{stage.lower} 到 {stage.upper}"
                for stage in AFFECTION_STAGES
            ),
            role_name=role.name or role.id,
            role_description=role.description.strip() or "（无）",
            role_prompt=self._sources.compile_role_prompt(role_id),
            self_text=self._sources.read_self(role_id).strip() or "（空）",
            memory_text=memory.strip() or "（空）",
            recent_messages=render_recent_messages(recent),
        )
