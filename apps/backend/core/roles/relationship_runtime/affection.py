"""好感度的阶段常量与纯状态迁移规则。

好感范围是 -100–100。所有好感变化都由 ``apply_affection_delta`` 计算：结果夹在
[阶段下限, 100]。达到过「熟悉」及以上之后，阶段下限是已达到的最高阶段的起点，
只升不降；在此之前（「陌生」与两个负向阶段）没有下限，好感可以自由降到 -100。
长时间未联系的衰减由 ``settle_affection_decay`` 按需补算，最多降到
max(阶段下限, 0)。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Literal

AFFECTION_MIN = -100
AFFECTION_MAX = 100

AffectionSource = Literal["init", "turn", "decay"]
"""一条好感历史的来源：AI 初始化、单轮对话结算、长时间未联系的衰减。"""
_SOURCES: frozenset[str] = frozenset({"init", "turn", "decay"})

AFFECTION_DECAY_GRACE = timedelta(days=3)
"""用户最后一条消息之后，这么久仍没有新消息就扣第一次。"""
AFFECTION_DECAY_INTERVAL = timedelta(days=1)
"""第一次之后，每再过这么久扣一次。"""
AFFECTION_DECAY_STEP = -1
AFFECTION_DECAY_REASON = "长时间没有联系"


@dataclass(frozen=True)
class AffectionStage:
    """一个固定好感阶段，``lower``/``upper`` 均为闭区间端点。"""

    name: str
    lower: int
    upper: int


AFFECTION_INTIMATE_STAGE = AffectionStage("亲密", 60, 79)
"""「亲密」阶段；其起点是寂寞增长与关系主动动机的好感门槛。"""

AFFECTION_FLOOR_STAGE = AffectionStage("熟悉", 20, 39)
"""「熟悉」阶段；达到过它及以上的阶段后才有阶段下限保护。"""

AFFECTION_STAGES: tuple[AffectionStage, ...] = (
    AffectionStage("厌恶", -100, -50),
    AffectionStage("冷淡", -49, -1),
    AffectionStage("陌生", 0, 19),
    AFFECTION_FLOOR_STAGE,
    AffectionStage("朋友", 40, 59),
    AFFECTION_INTIMATE_STAGE,
    AffectionStage("挚爱", 80, 100),
)
"""全局阶段定义（从低到高），不支持按角色配置。"""

_FLOOR_VALUES: frozenset[int] = frozenset(
    stage.lower
    for stage in AFFECTION_STAGES
    if stage.lower >= AFFECTION_FLOOR_STAGE.lower
)
"""合法的阶段下限：「熟悉」及以上各阶段的起点。"""
_LEGACY_STRANGER_FLOOR = 0
"""好感范围还是 0–100 时，没离开过「陌生」的角色存的阶段下限。"""


def affection_stage(value: int) -> AffectionStage:
    """返回 ``value`` 所在的阶段；超出 -100–100 视为调用方错误。"""
    for stage in AFFECTION_STAGES:
        if stage.lower <= value <= stage.upper:
            return stage
    raise ValueError(f"好感度超出范围: {value}")


def _stage_floor_of(value: int) -> int | None:
    """``value`` 所在阶段带来的下限：「熟悉」及以上是阶段起点，更低的阶段没有。"""
    lower = affection_stage(value).lower
    return lower if lower in _FLOOR_VALUES else None


def _merge_floor(current: int | None, reached: int | None) -> int | None:
    """两个下限中较高的一个；``None``（没有下限）低于任何下限。"""
    floors = [floor for floor in (current, reached) if floor is not None]
    return max(floors) if floors else None


@dataclass(frozen=True)
class AffectionState:
    """一个角色当前的好感状态；文件存在即代表已初始化。

    ``stage_floor`` 是好感不会再低于的值：达到过的最高「熟悉」及以上阶段的起点；
    从没达到过「熟悉」时为 ``None``，表示没有下限。
    ``updated_at`` 是好感值最近一次变化的时间。``last_user_message_at`` 是用户本人
    最近一条消息的时间，衰减从它开始计时；``decay_settled_at`` 是自那以后最近一次
    已结算衰减的到期时间，尚未结算过为 ``None``。
    """

    role_id: str
    value: int
    stage_floor: int | None
    initialized_at: str
    updated_at: str
    last_user_message_at: str
    decay_settled_at: str | None

    @classmethod
    def initial(cls, role_id: str, *, value: int, at: str) -> "AffectionState":
        """以 AI 判断的初始值建立状态；初始值在「熟悉」及以上时，阶段下限为所在阶段的起点。

        初始化发生在用户本人发消息的回合里，所以衰减也从这一刻开始计时。
        """
        return cls(role_id, value, _stage_floor_of(value), at, at, at, None)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AffectionState":
        """严格解析持久化内容；字段缺失或越界直接报错，不做默认值兜底。

        ``last_user_message_at`` 与 ``decay_settled_at`` 都是必填键，后者的值可以是
        ``null``。唯一的迁移：两个键**都**缺失的是衰减上线前（#710）保存的状态。
        那时好感只在初始化和用户本人的回合里变化，所以 ``updated_at`` 是最接近的
        用户消息时间，衰减从它开始计时、尚未结算过（#710 当天才合并，这类状态
        最多几小时，几乎不会立刻触发衰减）。只缺其中一个键属于损坏，直接报错。

        ``stage_floor`` 必须是 ``null`` 或「熟悉」及以上某阶段的起点（20/40/60/80），
        且不低于当前值所在阶段带来的下限。唯一的例外是 ``0``：好感范围还是 0–100
        （#749 之前）时，没离开过「陌生」的角色都存成 0，它的含义正是「没有下限」，
        读取时当作 ``None``，下次写入即存成 ``null``。
        """
        updated_at = _required_time(payload, "updated_at")
        timer_keys = {"last_user_message_at", "decay_settled_at"} & payload.keys()
        if not timer_keys:
            last_user_message_at, decay_settled_at = updated_at, None
        elif len(timer_keys) == 2:
            last_user_message_at = _required_time(payload, "last_user_message_at")
            decay_settled_at = (
                None
                if payload["decay_settled_at"] is None
                else _required_time(payload, "decay_settled_at")
            )
        else:
            raise ValueError(f"好感状态的衰减计时字段不完整: {sorted(timer_keys)}")
        state = cls(
            role_id=_required_text(payload, "role_id"),
            value=_required_int(payload, "value"),
            stage_floor=_stage_floor_field(payload),
            initialized_at=_required_time(payload, "initialized_at"),
            updated_at=updated_at,
            last_user_message_at=last_user_message_at,
            decay_settled_at=decay_settled_at,
        )
        if not AFFECTION_MIN <= state.value <= AFFECTION_MAX:
            raise ValueError(f"好感度超出范围: {state.value}")
        if state.stage_floor is not None and state.value < state.stage_floor:
            raise ValueError(f"好感度低于阶段下限: {state.value}")
        reached = _merge_floor(state.stage_floor, _stage_floor_of(state.value))
        if reached != state.stage_floor:
            raise ValueError(f"好感阶段下限低于当前阶段: {state.stage_floor}")
        return state

    def to_dict(self) -> dict[str, Any]:
        """返回持久化用的 JSON 对象。"""
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        """对外展示的好感摘要：数值、阶段名、阶段内进度（0–1）与阶段下限。

        ``floor`` 即 ``stage_floor``：好感不会再低于的值，没有下限时为 ``None``。
        """
        stage = affection_stage(self.value)
        progress = (self.value - stage.lower) / (stage.upper - stage.lower)
        return {
            "value": self.value,
            "stage": stage.name,
            "progress": progress,
            "floor": self.stage_floor,
        }


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
    """唯一的好感变化规则：值夹在 [阶段下限, 100]，没有下限时夹在 [-100, 100]。

    进入「熟悉」及以上阶段时阶段下限随之上升，只升不降。
    """
    lower = AFFECTION_MIN if state.stage_floor is None else state.stage_floor
    value = max(lower, min(AFFECTION_MAX, state.value + delta))
    floor = _merge_floor(state.stage_floor, _stage_floor_of(value))
    return replace(state, value=value, stage_floor=floor, updated_at=at)


def local_now(now: datetime | None = None) -> datetime:
    """把可选的 ``now`` 统一成带本地时区的时间；省略时取当前时间。"""
    return (now or datetime.now()).astimezone()


def record_user_message(state: AffectionState, *, at: str) -> AffectionState:
    """用户本人发来消息：衰减从 ``at`` 重新计时。调用方须先结算到 ``at`` 为止的衰减。"""
    return replace(state, last_user_message_at=at, decay_settled_at=None)


def settle_affection_decay(
    state: AffectionState, *, now: datetime
) -> tuple[AffectionState, list[AffectionHistoryEntry]]:
    """补算到 ``now`` 为止所有到期的衰减，返回新状态与要追加的历史。

    第 k 次（k 从 0 起）衰减在用户最后一条消息之后
    ``AFFECTION_DECAY_GRACE + k * AFFECTION_DECAY_INTERVAL`` 到期：恰好满 72 小时扣
    第一次（不是第 4 天），之后从最后一条消息起算、每满 24 小时再扣一次；按绝对
    时长计，不按日历日。旧状态的计时起点见 ``AffectionState.from_dict``。每次走 ``apply_affection_delta``，记录时间是它的到期
    时间，所以一次补算多天和逐日推进得到相同的状态与历史。衰减最多降到
    max(阶段下限, 0)，好感已经 ≤ 0 时不再衰减；被挡住的一次不写历史，但仍计入
    已结算，之后不会再补。
    """
    if state.decay_settled_at is not None:
        due = datetime.fromisoformat(state.decay_settled_at) + AFFECTION_DECAY_INTERVAL
    else:
        due = datetime.fromisoformat(state.last_user_message_at) + AFFECTION_DECAY_GRACE
    if due > now:
        return state, []
    # Decay never makes affection negative; a stage floor (>= 20) only raises that.
    decay_floor = 0 if state.stage_floor is None else state.stage_floor
    current = state
    entries: list[AffectionHistoryEntry] = []
    while True:
        if current.value <= decay_floor:
            # Only a user message raises the value again, and it restarts the
            # timer; every remaining due step is absorbed by the decay floor.
            due += ((now - due) // AFFECTION_DECAY_INTERVAL) * AFFECTION_DECAY_INTERVAL
            break
        at = due.astimezone().isoformat()
        stepped = apply_affection_delta(current, AFFECTION_DECAY_STEP, at=at)
        entries.append(
            AffectionHistoryEntry(
                at,
                current.value,
                stepped.value,
                stepped.value - current.value,
                AFFECTION_DECAY_REASON,
                "decay",
            )
        )
        current = stepped
        if due + AFFECTION_DECAY_INTERVAL > now:
            break
        due += AFFECTION_DECAY_INTERVAL
    return replace(current, decay_settled_at=due.astimezone().isoformat()), entries


def _stage_floor_field(payload: dict[str, Any]) -> int | None:
    """读取 ``stage_floor``；旧状态的 ``0`` 即「没有下限」，见 ``AffectionState.from_dict``。"""
    if "stage_floor" not in payload:
        raise ValueError("好感状态缺少 stage_floor")
    if payload["stage_floor"] is None:
        return None
    floor = _required_int(payload, "stage_floor")
    if floor == _LEGACY_STRANGER_FLOOR:
        return None
    if floor not in _FLOOR_VALUES:
        raise ValueError(f"好感阶段下限无效: {floor}")
    return floor


def _required_time(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"好感状态的 {key} 不是有效时间: {value}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"好感状态的 {key} 缺少时区: {value}")
    return value


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
