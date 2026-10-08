"""在 SELF 初始化流程中由对话模型判断角色的初始好感度。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from conversation.context_scope import load_user_context_threads
from core.memory.markdown import resolve_markdown_store
from session.manager import SessionManager
from shiori_sdk.json import load_json_object_loose

from ..model_runtime import RoleModelSnapshot
from ..models import RoleRecord
from ..role_prompt_compiler import RolePromptCompiler
from .affection import AFFECTION_MAX, AFFECTION_MIN, AFFECTION_STAGES
from .affection_service import RoleAffectionService
from .interaction import collect_user_recent_messages, render_recent_messages

_AFFECTION_SEED_SYSTEM = (
    "你在判断一个角色此刻对用户的初始好感度。只输出一个 JSON 对象，不要输出其他内容。"
)

_AFFECTION_SEED_PROMPT = """\
请根据以下资料，判断角色此刻对用户的初始好感度。

好感度是 {minimum}–{maximum} 的整数，分为以下阶段：
{stages}

判断规则：
- 以角色设定和 SELF.md 中 `## 我们的关系` 描述的关系基调为主要依据
- 设定里本来就亲密的关系可以从较高阶段开始；没有依据时不要虚构亲密
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


@dataclass(frozen=True)
class AffectionSeedSource:
    """初始化依据；新角色的长期记忆与近期互动只是默认内容或为空。"""

    self_text: str
    memory_text: str
    recent_messages: str


class LlmAffectionSeedGenerator:
    """Asks the dialogue snapshot for the initial affection and validates it strictly."""

    async def agenerate(
        self,
        role: RoleRecord,
        source: AffectionSeedSource,
        snapshot: RoleModelSnapshot,
    ) -> AffectionSeed:
        """Returns the seed, raising on provider failure or any invalid response."""
        prompt = _AFFECTION_SEED_PROMPT.format(
            minimum=AFFECTION_MIN,
            maximum=AFFECTION_MAX,
            stages="\n".join(
                f"- {stage.name} {stage.lower}–{stage.upper}"
                for stage in AFFECTION_STAGES
            ),
            role_name=role.name or role.id,
            role_description=role.description.strip() or "（无）",
            role_prompt=RolePromptCompiler().compile(role).content,
            self_text=source.self_text.strip() or "（空）",
            memory_text=source.memory_text.strip() or "（空）",
            recent_messages=source.recent_messages,
        )
        response = await snapshot.provider.chat(
            messages=[
                {"role": "system", "content": _AFFECTION_SEED_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            tools=[],
            model=snapshot.model,
            max_tokens=None,
        )
        return parse_affection_seed(response.content or "")


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

    def __init__(
        self,
        workspace: Path,
        *,
        session_manager: SessionManager,
        generator: LlmAffectionSeedGenerator,
    ) -> None:
        self._workspace = Path(workspace)
        self._session_manager = session_manager
        self._generator = generator
        self._affection = RoleAffectionService(workspace)

    async def ensure_initialized(
        self,
        role: RoleRecord,
        snapshot: RoleModelSnapshot,
        *,
        now: datetime | None = None,
    ) -> None:
        """Seeds affection when missing; failures propagate and leave it uninitialized.

        Every attempt sees the same evidence: profile, SELF.md, MEMORY.md and the
        user's own recent conversation, whatever path led to SELF being ready.
        """
        if self._affection.read_state(role.id) is not None:
            return
        source = self._seed_source(role.id)
        seed = await self._generator.agenerate(role, source, snapshot)
        self._affection.initialize(
            role.id, value=seed.value, reason=seed.reason, now=now
        )

    def _seed_source(self, role_id: str) -> AffectionSeedSource:
        store = resolve_markdown_store(workspace=self._workspace, role_id=role_id)
        session = self._session_manager.get_or_create(
            self._session_manager.role_session_key(role_id)
        )
        recent = collect_user_recent_messages(
            session.messages,
            user_threads=load_user_context_threads(self._workspace, role_id),
        )
        return AffectionSeedSource(
            self_text=store.read_self(),
            memory_text=store.read_long_term(),
            recent_messages=render_recent_messages(recent),
        )
