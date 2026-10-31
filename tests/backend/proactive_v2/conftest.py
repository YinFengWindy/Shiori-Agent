"""
共享测试设施：FakeStateStore、FakeRng、FakeLLM、make_proactive_pipeline、cfg_with
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import AsyncMock, MagicMock
from tests.support.generation_getters import bound_affection, run_in_turn

from agent.core.turn_events import core_kernel
from agent.tools.execution import ToolExecutionRequest, ToolExecutor
from agent.turns.proactive_sequence import current_proactive_reply
from agent.turns.reply_interruption import (
    ReplyInterruption,
    ReplyPlanInvalidated,
    reply_was_invalidated,
)
from conversation.initiated import _turn_result
from core.roles.reply_state import validate_role_reply
from shiori_sdk.core.conversation import InitiatedDelivery
from shiori_sdk.core.proactive_host import (
    NaturalReplyInvalidated,
    ProactiveToolCall,
    ProactiveToolOutcome,
    RoleReplyState,
    ValidatedRoleReply,
)
from proactive_v2.config import ProactiveConfig
from proactive_v2.gateway import GatewayDeps
from proactive_v2.tools import ToolDeps
from agent.looping.ports import SessionServices
from agent.turns.outbound import DeliveryReceipt, OutboundDispatch
from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateChain,
    ProactiveGateCompletion,
    ProactiveGateContext,
    ProactiveGateDecision,
    ProactiveMode,
)
from agent.core.proactive_turn.strategies import RelationshipStrategy
from tests.support.bound_chat_delivery import bound_chat_orchestrator

# ── FakeStateStore ────────────────────────────────────────────────────────


class FakeStateStore:
    """ProactiveStateStore 的最小 fake，只实现主动 pipeline 需要的接口。"""

    def __init__(self):
        self._delivery_count: int = 0
        self._is_dup: bool = False
        self._last_context_only_at: datetime | None = None
        self._ctx_only_count: int = 0
        self.context_only_send_marked: bool = False
        self._last_drift_at: datetime | None = None
        self.drift_run_marked: bool = False
        self._deliveries: list[str] = []
        self.tick_log_starts: list[dict[str, Any]] = []
        self.tick_log_finishes: list[dict[str, Any]] = []
        self.tick_step_logs: list[dict[str, Any]] = []

    # pre-gate
    def count_deliveries_in_window(self, session_key: str, window_hours: int) -> int:
        return self._delivery_count

    # post-guard
    def is_delivery_duplicate(
        self, session_key: str, delivery_key: str, window_hours: int
    ) -> bool:
        return self._is_dup

    def mark_delivery(self, session_key: str, delivery_key: str) -> None:
        self._deliveries.append(delivery_key)

    # context gate
    def get_last_context_only_at(self, session_key: str) -> datetime | None:
        return self._last_context_only_at

    def count_context_only_in_window(self, session_key: str, window_hours: int) -> int:
        return self._ctx_only_count

    def mark_context_only_send(self, session_key: str) -> None:
        self.context_only_send_marked = True

    def get_last_drift_at(self, session_key: str) -> datetime | None:
        return self._last_drift_at

    def mark_drift_run(self, session_key: str, now: datetime | None = None) -> None:
        self._last_drift_at = now
        self.drift_run_marked = True

    def record_tick_log_start(self, **payload: Any) -> None:
        self.tick_log_starts.append(payload)

    def record_tick_log_finish(self, **payload: Any) -> None:
        self.tick_log_finishes.append(payload)

    def record_tick_step_log(self, **payload: Any) -> None:
        self.tick_step_logs.append(payload)

    # helpers
    def set_delivery_count(self, n: int) -> None:
        self._delivery_count = n

    def set_is_duplicate(self, v: bool) -> None:
        self._is_dup = v

    def set_last_context_only_at(self, dt: datetime | None) -> None:
        self._last_context_only_at = dt

    def set_context_only_count(self, n: int) -> None:
        self._ctx_only_count = n

    def set_last_drift_at(self, dt: datetime | None) -> None:
        self._last_drift_at = dt


# ── FakeRng ───────────────────────────────────────────────────────────────


class FakeRng:
    def __init__(self, value: float = 0.5):
        self._value = value

    def random(self) -> float:
        return self._value


# ── FakeAckSink ──────────────────────────────────────────────────────────


class FakeAckSink:
    """记录所有 ACK 调用的 (compound_key, ttl_hours) 对。"""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, compound_key: str, ttl_hours: int) -> None:
        self.calls.append((compound_key, ttl_hours))

    def acked(self, key: str, ttl: int) -> bool:
        return (key, ttl) in self.calls

    def ttls_for(self, key: str) -> list[int]:
        return [ttl for k, ttl in self.calls if k == key]

    def not_acked(self, key: str) -> bool:
        return all(k != key for k, _ in self.calls)

    def all_keys(self) -> set[str]:
        return {k for k, _ in self.calls}


# ── FakeAlertAckSink ─────────────────────────────────────────────────────


class FakeAlertAckSink:
    """记录 alert_ack_fn 调用的 compound_key 列表（无 TTL）。"""

    def __init__(self):
        self.keys: list[str] = []

    async def __call__(self, compound_key: str) -> None:
        self.keys.append(compound_key)

    def all_keys(self) -> set[str]:
        return set(self.keys)

    def called_with(self, key: str) -> bool:
        return key in self.keys


class _FakeSession:
    def __init__(self, key: str) -> None:
        self.key = key
        self.messages: list[dict[str, object]] = []
        self.metadata: dict[str, Any] = {}
        self.last_consolidated = 0

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
        include: object = None,
    ) -> list[dict[str, object]]:
        return self.messages[-max_messages:]

    def add_message(self, role: str, content: str, media=None, **kwargs) -> None:
        msg: dict[str, object] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if media:
            msg["media"] = list(media)
        msg.update(kwargs)
        self.messages.append(msg)


# ── FakeLLM ──────────────────────────────────────────────────────────────


class FakeLLM:
    """预定义工具调用序列。序列耗尽后返回 None（loop 自然结束）。"""

    def __init__(self, sequence: list[tuple[str, dict]]):
        self._sequence = list(sequence)
        self._index = 0
        self.calls: list[list[dict]] = []  # 每次 llm 调用收到的 messages
        self.tool_choices: list[str | dict] = []  # 每次调用传入的 tool_choice

    async def __call__(
        self,
        messages: list[dict],
        schemas: list[dict],
        tool_choice: str | dict = "auto",
    ) -> dict | None:
        self.calls.append(list(messages))
        self.tool_choices.append(tool_choice)
        if self._index >= len(self._sequence):
            return None
        name, args = self._sequence[self._index]
        self._index += 1
        return {"name": name, "input": args}


# ── cfg_with ──────────────────────────────────────────────────────────────


def cfg_with(**kwargs) -> ProactiveConfig:
    """从默认 ProactiveConfig 创建，只覆盖指定字段。"""
    return ProactiveConfig(**kwargs)


# ── make_proactive_pipeline ─────────────────────────────────────────────────

GateEvaluator = Callable[[str, datetime], tuple[bool, dict[str, Any]]]


def _always_trigger(_session_key: str, _now_utc: datetime):
    return True, {"reason": "threshold"}


def relationship_gate_chain(
    *,
    loneliness_evaluate: GateEvaluator | None = _always_trigger,
    scene_evaluate: GateEvaluator | None = None,
    on_scene_delivered: Callable[[str, datetime], None] | None = None,
    on_scene_closed: Callable[[str], None] | None = None,
) -> ProactiveGateChain:
    class _SceneGate(ProactiveGateAdapter):
        name = "test.scene_followup"
        priority = 100

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            if scene_evaluate is None:
                return ProactiveGateDecision.continue_()
            should_follow_up, metadata = scene_evaluate(ctx.session_key, ctx.now_utc)
            if not should_follow_up:
                return ProactiveGateDecision.continue_()
            return ProactiveGateDecision.activate(
                ProactiveMode.SCENE_FOLLOWUP,
                reason="scene_followup",
                metadata=metadata,
            )

        def finalize(self, completion: ProactiveGateCompletion) -> None:
            if completion.outcome == "delivered" and on_scene_delivered is not None:
                on_scene_delivered(completion.session_key, completion.occurred_at)
            elif completion.outcome == "closed" and on_scene_closed is not None:
                on_scene_closed(completion.session_key)

    gates: list[ProactiveGateAdapter] = [_SceneGate()]
    if loneliness_evaluate is not None:
        runtime = SimpleNamespace(should_trigger_proactive=loneliness_evaluate)
        gates.append(RelationshipStrategy(bound_affection(runtime)))
    return ProactiveGateChain(motives=gates)


class _ReplyTicket:
    def __init__(self) -> None:
        self.interruption = ReplyInterruption()

    def invalidate(self) -> None:
        self.interruption.invalidate()


class _PipelineHost:
    """The port surface the pipeline tests drive through their orchestrator.

    ``pipeline_ref`` is filled after the pipeline exists, because the dispatcher
    test replaces ``_turn_orchestrator`` before the tick runs.
    """

    def __init__(self, pipeline_ref: dict[str, Any], tool_deps: ToolDeps) -> None:
        self._pipeline_ref = pipeline_ref
        self._tool_deps = tool_deps

    def _orchestrator(self) -> Any:
        return self._pipeline_ref["pipeline"]._turn_orchestrator

    def reply_state(self, role_id: str) -> RoleReplyState:
        del role_id
        orchestrator = self._orchestrator()
        if orchestrator is None:
            return RoleReplyState(moods=("平静",), mood_updated_at="")
        captured = orchestrator.capture_reply_context(
            self._pipeline_ref["pipeline"]._session_key
        )
        return RoleReplyState(
            moods=tuple(captured.moods),
            mood_updated_at=captured.previous_updated_at,
        )

    def natural_chat_enabled(self, session_key: str) -> bool:
        orchestrator = self._orchestrator()
        if orchestrator is None:
            return False
        return bool(orchestrator.natural_chat_enabled(session_key))

    def begin_natural_reply(self) -> _ReplyTicket:
        return _ReplyTicket()

    @asynccontextmanager
    async def natural_reply_scope(
        self, ticket, session_key, channel, chat_id, *, turn_id
    ):
        orchestrator = self._orchestrator()
        async with orchestrator.natural_reply_scope(
            session_key,
            channel,
            chat_id,
            turn_id=turn_id,
            interruption=ticket.interruption,
        ):
            try:
                yield
            except ReplyPlanInvalidated as exc:
                raise NaturalReplyInvalidated(str(exc)) from exc
            finally:
                await orchestrator.commit_proactive_tool_facts(session_key)

    def reply_invalidated(self) -> bool:
        return reply_was_invalidated()

    def natural_reply_active(self) -> bool:
        return current_proactive_reply() is not None

    async def retarget_natural_reply(self, session_key: str, target) -> None:
        await self._orchestrator().retarget_natural_reply(session_key, dict(target))

    async def retarget_natural_transport(
        self, session_key: str, channel: str, chat_id: str
    ) -> None:
        await self._orchestrator().retarget_natural_transport(
            session_key, channel, chat_id
        )

    async def deliver(self, reply) -> InitiatedDelivery:
        return await self._commit(reply, include_target=True)

    async def commit_natural_reply(self, reply) -> InitiatedDelivery:
        return await self._commit(reply, include_target=False)

    async def _commit(self, reply, *, include_target: bool) -> InitiatedDelivery:
        committed: list[str] = []
        complete = await self._orchestrator().handle_proactive_turn(
            result=_turn_result(reply, include_target=include_target),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
            committed=committed,
        )
        return InitiatedDelivery(message_ids=tuple(committed), complete=bool(complete))

    async def execute_tool(
        self, call: ProactiveToolCall, invoker
    ) -> ProactiveToolOutcome:
        result = await ToolExecutor(core_kernel).execute(
            ToolExecutionRequest(
                call_id=call.call_id,
                tool_name=call.name,
                arguments=dict(call.arguments),
                source="proactive",
                session_key=call.session_key,
                channel=call.channel,
                chat_id=call.chat_id,
            ),
            invoker,
        )
        return ProactiveToolOutcome(
            text=str(result.output),
            status=result.status,
            arguments=result.final_arguments,
            finalize=result.finalize,
        )

    def tool_schemas(self, names=None):
        shared = getattr(self._tool_deps, "shared_tools", None)
        if shared is None:
            return ()
        return tuple(shared.get_schemas(None if names is None else list(names)))

    def mcp_server_names(self) -> tuple[str, ...]:
        shared = getattr(self._tool_deps, "shared_tools", None)
        if shared is None:
            return ()
        return tuple(sorted(shared.get_mcp_server_names()))

    def recent_activity(self, role_id: str, *, now: datetime) -> str:
        del role_id, now
        return ""

    def validate_reply(
        self,
        role_id: str,
        *,
        content: str,
        mood: str,
        thought: str,
        allow_empty_content: bool = False,
    ) -> ValidatedRoleReply:
        del role_id
        reply = validate_role_reply(
            {"content": content, "mood": mood, "thought": thought},
            ("平静",),
            allow_empty_content=allow_empty_content,
        )
        return ValidatedRoleReply(
            content=reply.content, mood=reply.mood, thought=reply.thought
        )

    def require_channel_account(self, role_id: str, channel: str) -> None:
        from agent.tools.account_delivery import shared_account_delivery

        delivery = shared_account_delivery(self._tool_deps.shared_tools)
        if delivery is None:
            raise RuntimeError("账号目标发送服务不可用")
        delivery.channel_account(channel, role_id)


def make_proactive_pipeline(
    *,
    cfg: ProactiveConfig | None = None,
    session_key: str = "test_session",
    state_store: FakeStateStore | None = None,
    any_action_gate: Any = None,
    passive_busy_fn: Any = None,
    sender: Any = None,
    deduper: Any = None,
    tool_deps: ToolDeps | None = None,
    gateway_deps: GatewayDeps | None = None,
    llm_fn: Any = None,
    rng: Any = None,
    recent_proactive_fn: Any = None,
    workspace_context_fn: Any = None,
    drift_pipeline: Any = None,
    target_transport_fn: Any = lambda: ("telegram", "test_chat_id"),
    proactive_gates: ProactiveGateChain | None = None,
    bind_getters: bool = True,
):
    from agent.core.proactive_turn import (
        ProactiveTurnPipeline,
        ProactiveTurnPipelineDeps,
    )

    # 合理的默认值：所有 gate 都放行
    if state_store is None:
        state_store = FakeStateStore()
        state_store.set_delivery_count(0)

    if any_action_gate is None:
        gate = MagicMock()
        gate.should_act.return_value = (True, {})
        any_action_gate = gate

    if sender is None:
        sender = AsyncMock()
        sender.send.return_value = True

    if deduper is None:
        deduper = AsyncMock()
        deduper.is_duplicate = AsyncMock(return_value=(False, ""))

    if tool_deps is None:
        tool_deps = ToolDeps(
            recent_chat_fn=AsyncMock(return_value=[]),
        )
    if gateway_deps is None:
        gateway_deps = GatewayDeps(
            alert_fn=AsyncMock(return_value=[]),
            feed_fn=AsyncMock(return_value=[]),
            context_fn=AsyncMock(return_value=[]),
            web_fetch_tool=tool_deps.web_fetch_tool,
            max_chars=tool_deps.max_chars,
            content_limit=(
                cfg.agent_tick_content_limit
                if cfg
                else ProactiveConfig().agent_tick_content_limit
            ),
        )

    if rng is None:
        rng = FakeRng(value=0.0)  # 默认打开 context_fallback，避免空候选直接早退

    if proactive_gates is None:
        proactive_gates = relationship_gate_chain()

    pipeline_ref: dict[str, Any] = {}
    host = _PipelineHost(pipeline_ref, tool_deps)
    if tool_deps.proactive_host is None:
        tool_deps.proactive_host = host

    session = _FakeSession(session_key)

    async def append_messages(session, messages, **kwargs):
        before_commit = kwargs.get("before_commit")
        if before_commit is not None and not await before_commit():
            return False
        # Persistence stamps an id onto each stored draft. The port reads it.
        for index, message in enumerate(messages):
            if not str(message.get("id") or "").strip():
                message["id"] = f"{session.key}:{len(session.messages) + index}"
        session.messages.extend(messages)
        session.metadata.update(kwargs.get("metadata_updates") or {})
        return True

    session_manager = SimpleNamespace(
        get_or_create=lambda _key: session,
        append_messages=AsyncMock(side_effect=append_messages),
    )
    session_svc = SessionServices(
        session_manager=cast(Any, session_manager),
        presence=cast(
            Any, SimpleNamespace(record_initiated_sent=lambda _key, _when: None)
        ),
    )

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
            sent = await sender.send(outbound.content)
            return DeliveryReceipt.sent() if sent else None

    # The default "telegram" target is a bound private chat: the account sends
    # it through ``sender`` just as the outbound port does for the desktop.
    orchestrator, _ = bound_chat_orchestrator(
        session_svc, _Outbound(), deliver=lambda content: sender.send(content)
    )

    pipeline = ProactiveTurnPipeline(
        ProactiveTurnPipelineDeps(
            cfg=cfg or cfg_with(),
            session_key=session_key,
            state_store=state_store,
            any_action_gate=any_action_gate,
            passive_busy_fn=passive_busy_fn,
            turn_orchestrator=orchestrator,
            deduper=deduper,
            tool_deps=tool_deps,
            gateway_deps=gateway_deps,
            role_prompt_fn=lambda: "测试角色提示词",
            llm_fn=llm_fn,
            rng=rng,
            recent_proactive_fn=recent_proactive_fn,
            workspace_context_fn=workspace_context_fn,
            drift_pipeline=drift_pipeline,
            kernel=core_kernel,
            proactive_host=host,
            target_transport_fn=target_transport_fn,
            proactive_gates=proactive_gates,
        )
    )
    pipeline_ref["pipeline"] = pipeline
    if not bind_getters:
        return pipeline
    # Production ticks run under the generation lease, which carries both
    # getters; here both sockets are empty (plugins off).
    return run_in_turn(pipeline)
