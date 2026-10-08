"""好感度的阶段常量与纯状态迁移规则。

所有好感变化都由 ``apply_affection_delta`` 计算：结果夹在 [阶段下限, 100]，
阶段下限是已达到的最高阶段的起点，只升不降。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

AFFECTION_MIN = 0
AFFECTION_MAX = 100

AffectionSource = Literal["init", "turn", "decay"]
"""一条好感历史的来源：AI 初始化、单轮对话结算、长时间未联系的衰减。"""
_SOURCES: frozenset[str] = frozenset({"init", "turn", "decay"})


@dataclass(frozen=True)
class AffectionStage:
    """一个固定好感阶段，``lower``/``upper`` 均为闭区间端点。"""

    name: str
    lower: int
    upper: int


AFFECTION_STAGES: tuple[AffectionStage, ...] = (
    AffectionStage("陌生", 0, 19),
    AffectionStage("熟悉", 20, 39),
    AffectionStage("朋友", 40, 59),
    AffectionStage("亲密", 60, 79),
    AffectionStage("挚爱", 80, 100),
)
"""全局阶段定义，不支持按角色配置。"""


def affection_stage(value: int) -> AffectionStage:
    """返回 ``value`` 所在的阶段；超出 0–100 视为调用方错误。"""
    for stage in AFFECTION_STAGES:
        if stage.lower <= value <= stage.upper:
            return stage
    raise ValueError(f"好感度超出范围: {value}")


@dataclass(frozen=True)
class AffectionState:
    """一个角色当前的好感状态；文件存在即代表已初始化。"""

    role_id: str
    value: int
    stage_floor: int
    initialized_at: str
    updated_at: str

    @classmethod
    def initial(cls, role_id: str, *, value: int, at: str) -> "AffectionState":
        """以 AI 判断的初始值建立状态，初始阶段下限为初始值所在阶段的起点。"""
        stage = affection_stage(value)
        return cls(role_id, value, stage.lower, at, at)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AffectionState":
        """严格解析持久化内容；字段缺失或越界直接报错，不做默认值兜底。"""
        state = cls(
            role_id=_required_text(payload, "role_id"),
            value=_required_int(payload, "value"),
            stage_floor=_required_int(payload, "stage_floor"),
            initialized_at=_required_text(payload, "initialized_at"),
            updated_at=_required_text(payload, "updated_at"),
        )
        if state.stage_floor not in {stage.lower for stage in AFFECTION_STAGES}:
            raise ValueError(f"好感阶段下限无效: {state.stage_floor}")
        if not state.stage_floor <= state.value <= AFFECTION_MAX:
            raise ValueError(f"好感度低于阶段下限或超出范围: {state.value}")
        return state

    def to_dict(self) -> dict[str, Any]:
        """返回持久化用的 JSON 对象。"""
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        """对外展示的好感摘要：数值、阶段名与阶段内进度（0–1）。"""
        stage = affection_stage(self.value)
        progress = (self.value - stage.lower) / (stage.upper - stage.lower)
        return {"value": self.value, "stage": stage.name, "progress": progress}


@dataclass(frozen=True)
class AffectionHistoryEntry:
    """好感历史中的一条记录；``init`` 记录没有变化前的值与变化量。"""

    time: str
    before: int | None
    after: int
    delta: int | None
    reason: str
    source: AffectionSource

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AffectionHistoryEntry":
        """严格解析一行历史；字段类型或来源不合法直接报错。"""
        source = payload.get("source")
        if source not in _SOURCES:
            raise ValueError(f"好感历史来源无效: {source}")
        return cls(
            time=_required_text(payload, "time", "好感历史"),
            before=_optional_int(payload, "before", "好感历史"),
            after=_required_int(payload, "after", "好感历史"),
            delta=_optional_int(payload, "delta", "好感历史"),
            reason=_required_text(payload, "reason", "好感历史"),
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        """返回写入 JSONL 的一行 JSON 对象。"""
        return asdict(self)


def apply_affection_delta(
    state: AffectionState, delta: int, *, at: str
) -> AffectionState:
    """唯一的好感变化规则：值夹在 [阶段下限, 100]，阶段下限随新阶段只升不降。"""
    value = max(state.stage_floor, min(AFFECTION_MAX, state.value + delta))
    floor = max(state.stage_floor, affection_stage(value).lower)
    return replace(state, value=value, stage_floor=floor, updated_at=at)


def _required_text(payload: dict[str, Any], key: str, subject: str = "好感状态") -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{subject}缺少 {key}")
    return value


def _required_int(payload: dict[str, Any], key: str, subject: str = "好感状态") -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{subject}的 {key} 必须是整数")
    return value


def _optional_int(payload: dict[str, Any], key: str, subject: str) -> int | None:
    if key not in payload:
        raise ValueError(f"{subject}缺少 {key}")
    return None if payload[key] is None else _required_int(payload, key, subject)
