"""角色关系快照提示词与优化器。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .models import RELATION_STATE_KEYS

if TYPE_CHECKING:
    from .service import RoleRelationshipRuntimeService

_RELATIONSHIP_SYSTEM = (
    "你正在根据当前关系证据，生成角色此刻对用户关系的主观状态。"
    "你只能输出 JSON 对象，不要输出 JSON 之外的文字。"
)
_RELATIONSHIP_PROMPT = """\
你要为当前角色生成一份运行时关系快照。

硬规则：
- `role_self_view` 必须是角色第一人称内心想法，必须使用“我”来表达，不能写成旁白或上帝视角。
- `relation_tags` 只能给 1 到 4 个短标签。
- `relation_state` 只能包含以下字段：<relation_state_fields>。
- `relation_state` 每个字段都必须是 0 到 1 的数字。
- `behavior_profile` 只能包含以下字段：loneliness_growth_base、loneliness_growth_when_unanswered、trigger_threshold、post_trigger_cooldown_minutes、night_suppression。
- `trigger_threshold` 使用 0 到 100 的数值。
- `night_suppression` 使用 0 到 1 的数值。
- 不要复述静态设定，不要分析系统机制，不要出现“角色”“用户”“设定”等旁白口吻。

输出 JSON 结构：
{{
  "role_self_view": "第一人称想法",
  "relation_tags": ["标签1", "标签2"],
  "relation_state": {{
<relation_state_example>
  }},
  "behavior_profile": {{
    "loneliness_growth_base": 0.0,
    "loneliness_growth_when_unanswered": 0.0,
    "trigger_threshold": 0.0,
    "post_trigger_cooldown_minutes": 0,
    "night_suppression": 0.0
  }}
}}

角色名称：
{role_name}

角色简介：
{role_description}

当前 SELF.md：
{self_text}

当前关系相关 MEMORY.md：
{memory_text}

最近互动：
{recent_messages}

主动互动摘要：
{interaction_summary}
"""
# relation_state 的字段清单与 JSON 示例都由 models 的 RELATION_STATE_KEYS 生成，避免两处维护。
_RELATIONSHIP_PROMPT = _RELATIONSHIP_PROMPT.replace(
    "<relation_state_fields>", "、".join(RELATION_STATE_KEYS)
).replace(
    "<relation_state_example>",
    ",\n".join(f'    "{key}": 0.0' for key in RELATION_STATE_KEYS),
)


class RelationshipSnapshotOptimizer:
    """Generates role relationship snapshots through the host dialogue model."""

    def __init__(self, runtime: RoleRelationshipRuntimeService) -> None:
        self._runtime = runtime
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def optimize(self, *, role_id: str) -> dict[str, Any]:
        """Generate a snapshot, recording and propagating failures to the caller."""
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id required for relationship optimizer")
        async with self._lock:
            now = datetime.now().astimezone()
            try:
                snapshot = await self._runtime.generate_snapshot_via_llm(
                    clean_role_id, now=now
                )
                self._runtime.recompute_loneliness(clean_role_id, now=now)
                return snapshot
            except Exception as exc:
                self._runtime.mark_snapshot_error(
                    clean_role_id,
                    error=str(exc),
                    attempted_at=now,
                )
                raise
