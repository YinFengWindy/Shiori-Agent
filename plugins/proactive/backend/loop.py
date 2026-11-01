"""
ProactiveLoop - 主动触达核心循环。

独立于 AgentLoop,定期:
  1. 拉取所有内容源的最新候选事件
  2. 获取用户最近聊天上下文
  3. 调用 LLM 反思:有没有值得主动说的
  4. 产出 TurnResult 并由统一 OutboundPort 发送消息
"""

from __future__ import annotations

import asyncio
import json
import logging
import random as _random_module
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from shiori_sdk.memory.engine import MemoryRetrievalApi
    from .memory_profile import MemoryProfile as MemoryProfileApi

from .turn.gates import ProactiveGate, ProactiveGateChain
from .traces import StrategyTraceType, build_strategy_trace_envelope
from .diagnostics import diagnostic_context, diagnostic_line
from .energy import (
    compute_energy,
    d_energy,
    next_tick_from_score,
)
from .judge import MessageDeduper
from .config import ProactiveConfig
from .memory_sampler import sample_memory_chunks
from .sensor import Sensor
from .state import ProactiveStateStore
from .target_selection import ProactiveTargetResolver
from .session_key import SessionWorkspace
from shiori_sdk.core.conversation import Conversation
from shiori_sdk.core.proactive_host import ProactiveHost
from shiori_sdk.core.sessions import Presence
from shiori_sdk.processes import Processes
from shiori_sdk.roles import Roles

logger = logging.getLogger(__name__)


class ProactiveLoop:
    _PROACTIVE_CONTEXT_FILE = "PROACTIVE_CONTEXT.md"
    _PROACTIVE_CONTEXT_TEMPLATE = """# Proactive Context

在这里写用户当前对主动推送的明确要求和规则。

- 主 agent 负责维护这份文件。
- proactive agent 每轮都会读取它,并把它视为需要遵守的规则,不是普通参考建议。
- 这里适合写白名单、黑名单、过滤条件、优先级、必须先验证的步骤。
- 这里不提供新闻事实,不提供候选内容,只定义规则。
- 写结论即可,不要写冗长过程。
"""

    def __init__(
        self,
        session_manager: SessionWorkspace,
        config: ProactiveConfig,
        *,
        proactive_host: ProactiveHost,
        conversation: Conversation,
        roles: Roles,
        role_prompt_fn: Callable[[], str],
        state_path: Path,
        processes: Processes | None = None,
        config_fn: Callable[[Roles], ProactiveConfig] | None = None,
        max_tokens: int = 1024,
        memory_store: "MemoryProfileApi | MemoryRetrievalApi | None" = None,
        presence: Presence | None = None,
        rng: _random_module.Random | None = None,
        passive_busy_fn: Callable[[str], bool] | None = None,
        proactive_motives: list[ProactiveGate] | None = None,
        tick_dispatcher: Callable[[Callable[[], Any]], Any] | None = None,
        affection_prompt_fn: Callable[[], str | None] | None = None,
        draft_prompt_fn: Callable[[], str | None] | None = None,
    ) -> None:
        """Model, tools, target reads, history and delivery go through
        ``proactive_host`` (``PROACTIVE_HOST``). ``conversation`` is this
        generation's ``CONVERSATION``; the tick copies its reply stamp from
        there. ``roles`` (``ROLES``) holds the role's ``proactive`` settings,
        whose switch decides whether a saved role is eligible.
        ``affection_prompt_fn`` renders the role's affection block (#714).

        ``config_fn`` rereads the role's config from ``roles`` before every
        tick: a tick whose switch is off is skipped, and a changed config
        rebuilds the tick pipeline. Nothing is opened until a tick runs: the
        state store at ``state_path``, the MCP pool (stdio sessions from
        ``processes``) and the feed poller start with the first tick that
        runs, and close again when a tick finds the switch off."""
        self._sessions = session_manager
        self._cfg = config
        self._config_fn = config_fn
        self._max_tokens = max_tokens
        self._state_path = state_path
        self._state: ProactiveStateStore | None = None
        self._processes = processes
        self._memory = memory_store
        self._presence = presence
        self._rng = rng
        self._passive_busy_fn = passive_busy_fn
        self._proactive_gates = ProactiveGateChain(motives=proactive_motives or ())
        self._tick_dispatcher = tick_dispatcher
        self._host = proactive_host
        self._conversation = conversation
        self._roles = roles
        self._affection_prompt_fn = affection_prompt_fn
        self._draft_prompt_fn = draft_prompt_fn
        self._role_prompt_fn = role_prompt_fn
        self._workspace_context_mtime_ns: int | None = None
        self._workspace_context_text: str = ""
        self._init_runtime_state()

    def _init_runtime_state(self) -> None:
        self._running = False
        self._stop_requested = asyncio.Event()
        self._poll_task: asyncio.Task[None] | None = None
        self._feed_poll_lock = asyncio.Lock()
        self._mcp_pool = self._make_mcp_pool()
        self._prepared = False

    @property
    def config(self) -> ProactiveConfig:
        """The config the last tick (or construction) read."""
        return self._cfg

    def _make_mcp_pool(self):
        """One pool for this role. Rebind keeps it; a new loop does not."""
        from .mcp_sources import McpClientPool

        workspace = getattr(self._sessions, "workspace", None)

        def open_session(name: str, command: Sequence[str], env: dict[str, str]):
            if self._processes is None:
                raise RuntimeError("MCP 会话需要宿主进程服务")
            return self._processes.mcp(name, list(command), dict(env))

        return McpClientPool(
            Path(workspace) if workspace else None, open_session=open_session
        )

    def rebind(
        self,
        *,
        sessions: SessionWorkspace,
        processes: Processes | None,
        conversation: Conversation,
        roles: Roles,
        max_tokens: int,
        memory_store: "MemoryProfileApi | MemoryRetrievalApi | None",
        presence: Presence | None,
        proactive_motives: list[ProactiveGate] | None,
        role_prompt_fn: Callable[[], str],
        passive_busy_fn: Callable[[str], bool] | None,
        affection_prompt_fn: Callable[[], str | None] | None,
        draft_prompt_fn: Callable[[], str | None] | None,
    ) -> None:
        """Point the next tick at the published generation.

        The MCP pool and this loop's task stay. A tick already inside
        ``run`` keeps the pipeline object it started with.
        """
        self._sessions = sessions
        self._processes = processes
        self._conversation = conversation
        self._roles = roles
        self._max_tokens = max_tokens
        self._memory = memory_store
        self._presence = presence
        self._proactive_gates = ProactiveGateChain(motives=proactive_motives or ())
        self._role_prompt_fn = role_prompt_fn
        self._passive_busy_fn = passive_busy_fn
        self._affection_prompt_fn = affection_prompt_fn
        self._draft_prompt_fn = draft_prompt_fn
        if self._prepared:
            self._init_runtime_components()

    def _require_state(self) -> ProactiveStateStore:
        if self._state is None:
            raise RuntimeError("主动状态库尚未打开")
        return self._state

    def _build_sense(self) -> Sensor:
        return Sensor(
            cfg=self._cfg,
            sessions=self._sessions,
            state=self._require_state(),
            memory=cast("MemoryProfileApi | None", self._memory),
            presence=self._presence,
            rng=self._rng,
            target_resolver=self._target_resolver,
            host=self._host,
        )

    def _build_target_resolver(self) -> ProactiveTargetResolver:
        """Selects each message's target from the role's live candidate sessions."""
        return ProactiveTargetResolver(roles=self._roles, host=self._host)

    def _build_agent_tick(self):
        from .agent_tick_factory import AgentTickDeps, AgentTickFactory

        # 1. 把 loop 级公共依赖收束成 AgentTickDeps。
        # 2. 交给 factory 组装出 ProactiveTurnPipeline（主动链路顶层抽象）。
        return AgentTickFactory(
            AgentTickDeps(
                cfg=self._cfg,
                sense=self._sense,
                max_tokens=self._max_tokens,
                memory=self._memory,
                state_store=self._require_state(),
                any_action_gate=None,
                passive_busy_fn=self._passive_busy_fn,
                deduper=self._message_deduper,
                rng=self._rng,
                workspace_context_fn=self._read_workspace_proactive_context,
                role_prompt_fn=self._role_prompt_fn,
                proactive_host=self._host,
                conversation=self._conversation,
                pool=self._mcp_pool,
                proactive_gates=self._proactive_gates,
                affection_prompt_fn=self._affection_prompt_fn,
                draft_prompt_fn=self._draft_prompt_fn,
            )
        ).build()

    def _build_message_deduper(self) -> MessageDeduper | None:
        if not self._cfg.message_dedupe_enabled:
            return None
        return MessageDeduper(
            host=self._host,
            max_tokens=self._max_tokens,
        )

    def _init_runtime_components(self) -> None:
        # 1. 准备主动规则面板文件（PROACTIVE_CONTEXT.md）。
        self._ensure_workspace_proactive_context_file()
        # 2. 预读规则面板内容并做缓存。
        self._read_workspace_proactive_context()
        # 3. 构建目标选择、传感器、去重器和主动链路 pipeline。
        self._target_resolver = self._build_target_resolver()
        self._sense = self._build_sense()
        self._message_deduper = self._build_message_deduper()
        self._proactive_pipeline = self._build_agent_tick()
        # 4. 启动时把当前 proactive 配置落一份 trace，方便回看。
        self._trace_proactive_config_snapshot()

    def _workspace_proactive_context_path(self) -> Path | None:
        return self._state_path.parent / self._PROACTIVE_CONTEXT_FILE

    def _ensure_workspace_proactive_context_file(self) -> None:
        path = self._workspace_proactive_context_path()
        if path is None or path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._PROACTIVE_CONTEXT_TEMPLATE, encoding="utf-8")

    def _read_workspace_proactive_context(self) -> str:
        path = self._workspace_proactive_context_path()
        if path is None:
            return ""
        self._ensure_workspace_proactive_context_file()
        try:
            stat = path.stat()
            mtime_ns = int(stat.st_mtime_ns)
            if self._workspace_context_mtime_ns == mtime_ns:
                return self._workspace_context_text
            text = path.read_text(encoding="utf-8").strip()
            self._workspace_context_mtime_ns = mtime_ns
            self._workspace_context_text = text
            return text
        except Exception as e:
            logger.warning("[proactive] 读取 workspace proactive context 失败: %s", e)
            return self._workspace_context_text

    def _trace_proactive_config_snapshot(self) -> None:
        payload = {
            "enabled": self._cfg.enabled,
            "score_llm_threshold": self._cfg.score_llm_threshold,
            "tick_interval_s0": self._cfg.tick_interval_s0,
            "tick_interval_s1": self._cfg.tick_interval_s1,
            "tick_jitter": self._cfg.tick_jitter,
            "memory_history_gate_enabled": self._cfg.memory_history_gate_enabled,
            "sleep_modifier_sleeping": self._cfg.sleep_modifier_sleeping,
        }
        self._append_trace_line("proactive_config_trace.jsonl", payload)

    def _trace_proactive_rate_decision(
        self,
        *,
        base_score: float | None,
        interval: int,
        mode: str,
    ) -> None:
        self._append_trace_line(
            "proactive_rate_trace.jsonl",
            {
                "mode": mode,
                "base_score": round(base_score, 4) if base_score is not None else None,
                "interval_seconds": int(interval),
                "score_llm_threshold": self._cfg.score_llm_threshold,
                "tick_interval_s0": self._cfg.tick_interval_s0,
                "tick_interval_s1": self._cfg.tick_interval_s1,
                "tick_jitter": self._cfg.tick_jitter,
            },
        )

    def _append_trace_line(self, filename: str, payload: dict[str, Any]) -> None:
        try:
            memory_dir = self._sessions.workspace / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            trace_file = memory_dir / filename
            if "trace_type" not in payload or "payload" not in payload:
                trace_type: StrategyTraceType = (
                    "proactive_config" if "config" in filename else "proactive_rate"
                )
                source = (
                    "proactive.config"
                    if trace_type == "proactive_config"
                    else "proactive.rate"
                )
                role_id = self._cfg.role_id
                payload = {
                    **build_strategy_trace_envelope(
                        trace_type=trace_type,
                        source=source,
                        subject_kind="role" if role_id else "global",
                        subject_id=role_id or filename.removesuffix(".jsonl"),
                        payload=payload,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    **payload,
                }
            with trace_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("[proactive] write trace failed %s: %s", filename, exc)

    async def _poll_feeds_once(self) -> None:
        """执行一次 feed 轮询,加锁保证不并发。
        MCP tool 层已将系统级失败序列化为 "error: ..." 字符串返回,
        此处统一检测并 warning 记录,不阻断 loop 主流程。
        """
        if self._feed_poll_lock.locked():
            logger.debug("[proactive] feed poll 仍在进行,跳过本次")
            return
        async with self._feed_poll_lock:
            try:
                from . import mcp_sources

                await mcp_sources.poll_content_feeds_async(self._mcp_pool)
                logger.info("[proactive] feed poll 完成")
            except Exception as e:
                logger.warning("[proactive] feed poll 系统级失败: %s", e)

    async def _poll_loop(self) -> None:
        """每配置间隔秒周期性触发 feed 轮询。"""
        while self._running:
            await self._wait_interval(
                max(1, int(self._cfg.feed_poller_interval_seconds))
            )
            if not self._running:
                break
            await self._poll_feeds_once()

    async def run(self) -> None:
        if self._stop_requested.is_set():
            return
        self._running = True
        logger.info("ProactiveLoop 已启动  角色=%s", self._cfg.role_id)
        try:
            await self._run_loop()
        finally:
            self.stop()
            await self._release()

    async def _prepare(self) -> None:
        """Opens what a running tick needs, once: state, pipeline, MCP, feeds.

        Connecting and the first feed poll sit inside ``run``'s cleanup
        boundary: a stop can cancel them after some servers are already up.
        """
        if self._prepared:
            return
        if self._state is None:
            self._state = ProactiveStateStore(self._state_path)
        self._init_runtime_components()
        self._prepared = True
        await self._mcp_pool.connect_all()
        # 首次 tick 前同步完成一次 feed 轮询，保证拿到新鲜数据
        await self._poll_feeds_once()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _release(self) -> None:
        """Closes what ``_prepare`` opened. A failed poll still propagates."""
        if not self._prepared and self._state is None:
            return
        self._prepared = False
        try:
            if self._poll_task is not None:
                poll_task, self._poll_task = self._poll_task, None
                await self._stop_poll_task(poll_task)
        finally:
            try:
                # Never leaks MCP connections.
                await self._mcp_pool.disconnect_all()
                logger.info("[proactive] mcp pool 已关闭")
            finally:
                state, self._state = self._state, None
                if state is not None:
                    state.close()

    async def _run_loop(self) -> None:
        last_base_score: float | None = None
        while self._running:
            if self._cfg.enabled:
                interval = self._next_interval(last_base_score)
                logger.info("[proactive] 下次 tick 间隔=%ds", interval)
            else:
                # Switched off: only check the switch again, without traces.
                interval = max(1, int(self._cfg.tick_interval_s1))
            await self._wait_interval(interval)
            if not self._running:
                break
            try:
                last_base_score = await self._run_tick()
            except Exception:
                logger.exception("ProactiveLoop tick 异常")
                last_base_score = None

    def _refresh_config(self) -> ProactiveConfig:
        """Rereads the role's config; a change rebuilds the open pipeline."""
        if self._config_fn is None:
            return self._cfg
        config = self._config_fn(self._roles)
        if config != self._cfg:
            self._cfg = config
            if self._prepared and config.enabled:
                self._init_runtime_components()
        return config

    async def _run_tick(self) -> float | None:
        """Runs one tick through the role's tick dispatcher, if the switch is on.

        A switched-off role skips the tick and closes what its last tick opened.
        """
        if not self._refresh_config().enabled:
            await self._release()
            return None
        await self._prepare()
        if self._tick_dispatcher is None:
            return await self._tick()
        return await self._tick_dispatcher(self._tick)

    def _next_interval(self, base_score: float | None = None) -> int:
        """根据 base_score 返回自适应等待秒数。无 presence 时回退固定间隔。"""
        if not self._presence:
            interval = self._cfg.interval_seconds
            self._trace_proactive_rate_decision(
                base_score=base_score,
                interval=interval,
                mode="fixed_no_presence",
            )
            return interval
        # base_score 由 _tick 传入;首次启动时用电量估算一个初始值
        if base_score is None:
            session_key = self._target_session_key()
            last_user_at = self._presence.last_user_at(session_key)
            energy = compute_energy(last_user_at)
            base_score = d_energy(energy) * self._cfg.score_weight_energy
        interval = next_tick_from_score(
            base_score,
            tick_s1=self._cfg.tick_interval_s1,
            tick_s0=self._cfg.tick_interval_s0,
            tick_jitter=self._cfg.tick_jitter,
            rng=self._rng,
        )
        self._trace_proactive_rate_decision(
            base_score=base_score,
            interval=interval,
            mode="adaptive",
        )
        return interval

    def _target_session_key(self) -> str:
        role_id = self._cfg.role_id
        return self._sessions.role_session_key(role_id) if role_id else ""

    def stop(self) -> None:
        """Stops scheduling ticks; the runtime owner cancels an in-flight tick.

        A cancelled tick abandons whatever it has not delivered yet; replies it
        already handed to the outbound queue are still sent by the dispatcher.
        """
        self._running = False
        self._stop_requested.set()

    @staticmethod
    async def _stop_poll_task(task: asyncio.Task[None]) -> None:
        """Interrupts an in-flight feed poll and re-raises any failure but its cancel."""
        task.cancel()
        await asyncio.wait([task])
        if not task.cancelled() and (error := task.exception()) is not None:
            raise error

    async def _wait_interval(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=seconds)
        except TimeoutError:
            pass

    def _sample_random_memory(self, n: int = 2) -> list[str]:
        """随机抽取 n 条记忆片段,无记忆时返回 []。"""
        if not self._memory:
            return []
        try:
            memory = cast("MemoryProfileApi", self._memory)
            bind_session_metadata = getattr(memory, "bind_session_metadata", None)
            target_session_key = self._target_session_key()
            role_id = (
                target_session_key.split(":", 1)[1]
                if target_session_key.startswith("role:")
                else ""
            )
            if callable(bind_session_metadata):
                bind_session_metadata({"role_id": role_id} if role_id else None)
            raw = str(memory.read_long_term() or "").strip()
            return sample_memory_chunks(raw, n=n)
        except Exception as e:
            logger.warning("[proactive] 随机记忆抽取失败: %s", e)
            return []

    def _has_role_memory(self) -> bool:
        return self._sense.has_role_memory()

    def _read_memory_text(self) -> str:
        return self._sense.read_memory_text()

    def _compute_energy(self) -> float:
        """计算目标 session 的当前电量(取目标与全局较高值)。"""
        return self._sense.compute_energy()

    def _compute_interruptibility(
        self,
        *,
        now_hour: int,
        now_utc: datetime,
        recent_msg_count: int,
    ) -> tuple[float, dict[str, float]]:
        """计算软打扰系数(0~1),并注入随机探索,避免长期锁死。"""
        return self._sense.compute_interruptibility(
            now_hour=now_hour,
            now_utc=now_utc,
            recent_msg_count=recent_msg_count,
        )

    # ── internal ──────────────────────────────────────────────────

    async def _tick(self) -> float | None:
        """执行一次 proactive v2 tick。"""
        # 主动回复全链路入口：Gate → Fetch → Judge → Resolve → Deliver。
        # Session attribution is set by ``PROACTIVE_HOST.run_tick``.
        started = time.perf_counter()
        session_key = self._target_session_key()
        with diagnostic_context(session=session_key, flow="proactive", phase="tick"):
            logger.info(
                diagnostic_line(
                    "ProactiveLoop._tick",
                    event="start",
                    flow="proactive",
                    phase="tick",
                    session=session_key,
                    action="run",
                )
            )
            try:
                score = await self._proactive_pipeline.run()
            except Exception as exc:
                logger.exception(
                    diagnostic_line(
                        "ProactiveLoop._tick",
                        event="phase_error",
                        flow="proactive",
                        phase="tick",
                        session=session_key,
                        action="fail",
                        reason="proactive_tick_error",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error_type=type(exc).__name__,
                        note=str(exc)[:160],
                    )
                )
                raise
            logger.info(
                diagnostic_line(
                    "ProactiveLoop._tick",
                    event="end",
                    flow="proactive",
                    phase="tick",
                    session=session_key,
                    action="done",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            return score
