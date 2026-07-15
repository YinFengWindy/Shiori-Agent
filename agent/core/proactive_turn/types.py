"""主动回复 pipeline 的共享结果与依赖契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from ..drift_turn import DriftTurnPipeline
from agent.tool_hooks import ToolHook
from agent.turns.orchestrator import TurnOrchestrator
from agent.turns.result import TurnResult
from proactive_v2.config import ProactiveConfig
from proactive_v2.gateway import GatewayDeps
from proactive_v2.tools import ToolDeps


@dataclass
class GateResult:
    """准入检查结果；blocked 为真时不进入后续阶段。"""

    blocked: bool
    reason: str
    base_score: float | None
    context_as_fallback_open: bool = False
    scene_followup_open: bool = False


@dataclass
class FeedResult:
    """数据拉取结果；进入 drift 时跳过 Judge 和 Resolve。"""

    drift_entered: bool
    base_score: float | None
    messages: list[dict] = field(default_factory=list)


@dataclass
class ResolveResult:
    """主动消息的最终裁定结果。"""

    action: str
    result: TurnResult


@dataclass
class ProactiveTurnPipelineDeps:
    """构造主动回复 pipeline 所需的依赖。"""

    cfg: ProactiveConfig
    session_key: str
    state_store: Any
    any_action_gate: Any | None
    last_user_at_fn: Callable[[], datetime | None]
    passive_busy_fn: Callable[[str], bool] | None
    turn_orchestrator: TurnOrchestrator | None
    deduper: Any | None
    tool_deps: ToolDeps
    gateway_deps: GatewayDeps | None
    workspace_context_fn: Callable[[], str] | None
    llm_fn: Any | None
    rng: Any | None
    recent_proactive_fn: Callable[[], list] | None
    drift_pipeline: DriftTurnPipeline | None
    target_transport_fn: Callable[[], tuple[str, str]] | None = None
    target_transports_fn: Callable[[], list[tuple[str, str]]] | None = None
    retry_wait_fn: Callable[[float], Awaitable[None]] | None = None
    tool_hooks: list[ToolHook] | None = None
    loneliness_gate_fn: Callable[[str, datetime], tuple[bool, dict[str, Any]]] | None = None
    scene_followup_gate_fn: Callable[[str, datetime], tuple[bool, dict[str, Any]]] | None = None
    scene_followup_sent_fn: Callable[[str, datetime], Any] | None = None
    scene_followup_closed_fn: Callable[[str], Any] | None = None
