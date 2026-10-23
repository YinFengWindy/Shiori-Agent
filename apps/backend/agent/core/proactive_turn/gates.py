"""Independently evaluated core proactive motives that may claim a tick."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from time import perf_counter
from typing import Literal, Mapping, Protocol, Sequence, cast, runtime_checkable


class ProactiveMode(StrEnum):
    """Core-owned modes that an official gate may activate."""

    SCENE_FOLLOWUP = "scene_followup"
    RELATIONSHIP_FALLBACK = "relationship_fallback"


@dataclass(frozen=True)
class ProactiveGateContext:
    """Read-only input supplied to a proactive gate for one tick."""

    tick_id: str
    session_key: str
    now_utc: datetime
    # The single (channel, chat_id) this tick delivers to.
    target_transport: tuple[str, str]


@dataclass(frozen=True)
class ProactiveGateDecision:
    """A gate either continues, blocks the tick, or claims one core mode."""

    kind: Literal["continue", "block", "activate"]
    reason: str = ""
    mode: ProactiveMode | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def continue_(
        cls, *, reason: str = "", metadata: Mapping[str, object] | None = None
    ) -> "ProactiveGateDecision":
        """Records a non-trigger without denying other motives or sources."""
        return cls(kind="continue", reason=reason, metadata=dict(metadata or {}))

    @classmethod
    def activate(
        cls,
        mode: ProactiveMode,
        *,
        reason: str,
        metadata: Mapping[str, object] | None = None,
    ) -> "ProactiveGateDecision":
        return cls(
            kind="activate",
            reason=reason,
            mode=mode,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class ProactiveGateActivation:
    """The one gate that claimed the current proactive tick."""

    gate_name: str
    mode: ProactiveMode
    reason: str
    metadata: Mapping[str, object]
    # The claiming instance receives the completion even if its plugin was
    # unloaded or reloaded after evaluation.
    gate: "ProactiveGate" = field(compare=False, repr=False)


def resolve_gate_attempt_index(gate: ProactiveGateActivation | None) -> int:
    """Returns the validated zero-based attempt index carried by a gate."""

    raw = gate.metadata.get("attempt_index", 0) if gate is not None else 0
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError("proactive gate attempt_index 必须是非负整数")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("proactive gate attempt_index 必须是非负整数") from exc
    if value < 0:
        raise ValueError("proactive gate attempt_index 必须是非负整数")
    return value


@dataclass(frozen=True)
class ProactiveGateCompletion:
    """Final outcome delivered to the gate that activated the tick."""

    activation: ProactiveGateActivation
    session_key: str
    occurred_at: datetime
    outcome: Literal["delivered", "closed"]
    reason: str = ""


@dataclass(frozen=True)
class ProactiveGateTraceItem:
    """One evaluated gate, retained in the tick trace for diagnosis."""

    gate_name: str
    priority: int
    decision: Literal["continue", "block", "activate"]
    reason: str
    metadata: Mapping[str, object]
    duration_ms: int


@dataclass(frozen=True)
class ProactiveGateResult:
    """The GateChain's complete result for one proactive tick."""

    reason: str
    activation: ProactiveGateActivation | None
    trace: tuple[ProactiveGateTraceItem, ...]


@runtime_checkable
class ProactiveGate(Protocol):
    """An official, side-effect-free proactive admission policy."""

    name: str
    priority: int

    def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision: ...

    def finalize(self, completion: ProactiveGateCompletion) -> None: ...


class ProactiveGateAdapter:
    """Convenience base for gates that do not need completion handling."""

    name = ""
    priority = 0

    def finalize(self, completion: ProactiveGateCompletion) -> None:
        _ = completion


class ProactiveGateChain:
    """Evaluates core motives by priority and routes selected-mode completion.

    Names are validated once at construction, so duplicates fail where the
    chain is wired. A motive may claim the tick but never block it.
    """

    def __init__(self, *, motives: Sequence[ProactiveGate] = ()) -> None:
        names: set[str] = set()
        for gate in motives:
            name = str(gate.name).strip()
            if not name:
                raise ValueError("Proactive gate name must not be empty")
            if name in names:
                raise ValueError(f"Duplicate proactive gate name: {name}")
            names.add(name)
        self._ordered = tuple(
            sorted(motives, key=lambda gate: (-int(gate.priority), gate.name))
        )

    def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateResult:
        trace: list[ProactiveGateTraceItem] = []
        for gate in self._ordered:
            started = perf_counter()
            decision = gate.evaluate(ctx)
            duration_ms = int((perf_counter() - started) * 1000)
            self._validate_decision(gate, decision)
            if decision.kind == "block":
                raise ValueError(
                    f"Core motive {gate.name} cannot block global admission"
                )
            trace.append(
                ProactiveGateTraceItem(
                    gate_name=gate.name,
                    priority=gate.priority,
                    decision=decision.kind,
                    reason=decision.reason,
                    metadata=dict(decision.metadata),
                    duration_ms=duration_ms,
                )
            )
            if decision.kind == "activate":
                # _validate_decision 已保证 activate 分支下 mode 不为空；
                # 这里仅做静态类型收窄，不再重复运行期校验。
                mode = cast(ProactiveMode, decision.mode)
                return ProactiveGateResult(
                    reason=decision.reason or gate.name,
                    activation=ProactiveGateActivation(
                        gate_name=gate.name,
                        mode=mode,
                        reason=decision.reason,
                        metadata=dict(decision.metadata),
                        gate=gate,
                    ),
                    trace=tuple(trace),
                )
        return ProactiveGateResult(
            reason="passed",
            activation=None,
            trace=tuple(trace),
        )

    def finalize(self, completion: ProactiveGateCompletion) -> None:
        """Routes the outcome to the gate instance that claimed the tick."""
        completion.activation.gate.finalize(completion)

    @staticmethod
    def _validate_decision(
        gate: ProactiveGate,
        decision: ProactiveGateDecision,
    ) -> None:
        if not isinstance(decision, ProactiveGateDecision):
            raise TypeError(
                f"Proactive gate {gate.name} returned an invalid decision: "
                f"{type(decision).__name__}"
            )
        if decision.kind not in {"continue", "block", "activate"}:
            raise ValueError(
                f"Proactive gate {gate.name} returned an unknown decision: "
                f"{decision.kind}"
            )
        if decision.kind == "activate" and decision.mode is None:
            raise ValueError(f"Proactive gate {gate.name} activated without a mode")
        if decision.kind != "activate" and decision.mode is not None:
            raise ValueError(f"Proactive gate {gate.name} supplied an invalid mode")
