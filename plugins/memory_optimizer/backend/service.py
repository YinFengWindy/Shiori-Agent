"""The process-wide optimization loop, shared by every generation of the plugin.

Each generation's setup attaches its host services (a ``OptimizerBinding``);
the loop always runs on the published generation's binding, or the newest one
while none is published yet. A generation that retires while it runs a role
has that run cancelled (the pending facts go back) and the role runs again on
the current binding.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextvars import Context
from dataclasses import dataclass
from datetime import datetime, timedelta

from shiori_sdk.core.markdown_memory import MarkdownMemory
from shiori_sdk.core.memory_optimizer import MemoryOptimizationRun
from shiori_sdk.models import RoleModels
from shiori_sdk.roles import Roles

from .config import DEFAULT_INTERVAL_SECONDS
from .optimizer import LAST_OPTIMIZED_STATE_KEY, MemoryOptimizer, self_rewrite_pending

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class OptimizerBinding:
    """One generation's host services. ``is_active`` tells whether it is published."""

    roles: Roles
    memory: MarkdownMemory
    models: RoleModels
    is_active: Callable[[], bool]


def _report_loop_death(task: asyncio.Task[None]) -> None:
    """Logs the loop's failure when it happens; ``close`` raises it later."""
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("[memory_optimizer] 整理循环异常退出", exc_info=error)


class MemoryOptimizerService:
    """Optimizes every role once per interval, aligned to the interval's boundaries.

    Idle when constructed. The first ``attach`` starts the loop: it first
    optimizes the roles that are overdue (never optimized, optimized longer
    than an interval ago, or whose SELF.md still waits for the current writing
    rules), then every role at each boundary. ``close`` (plugin disabled or
    process exit) stops the loop and cancels the running optimization.
    """

    def __init__(
        self,
        optimizer: MemoryOptimizer | None = None,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._optimizer = optimizer or MemoryOptimizer()
        self._now = now_fn or datetime.now
        self._interval = DEFAULT_INTERVAL_SECONDS
        self._bindings: list[OptimizerBinding] = []
        self._bound = asyncio.Event()
        self._rescheduled = asyncio.Event()
        self._loop: asyncio.Task[None] | None = None
        self._in_flight: tuple[OptimizerBinding, asyncio.Task[None]] | None = None
        self._run: MemoryOptimizationRun | None = None
        self._closed = False

    def attach(
        self, binding: OptimizerBinding, *, interval_seconds: int
    ) -> Callable[[], None]:
        """Adds a generation's services and returns its detach.

        ``interval_seconds`` replaces the current interval; the wait for the
        next boundary is recomputed.
        """
        if self._closed:
            raise RuntimeError("记忆整理服务已关闭")
        self._bindings.append(binding)
        self._bound.set()
        if interval_seconds != self._interval:
            self._interval = interval_seconds
            self._rescheduled.set()
        if self._loop is None:
            # A fresh context: the loop outlives the generation that started it.
            self._loop = asyncio.create_task(
                self._run_forever(), name="memory_optimizer:loop", context=Context()
            )
            self._loop.add_done_callback(_report_loop_death)
            logger.info(
                "[memory_optimizer] 整理循环已启动，间隔=%ds (%.1fh)，对齐整点",
                self._interval,
                self._interval / 3600,
            )
        return lambda: self._detach(binding)

    def active_run(self) -> MemoryOptimizationRun | None:
        """The role being optimized now (``MEMORY_OPTIMIZER``)."""
        return self._run

    async def close(self) -> None:
        """Stops the loop; a running optimization is cancelled and rolled back.

        Raises the loop's failure if it died before, so the host reports it.
        """
        self._closed = True
        self._bindings.clear()
        loop = self._loop
        if loop is None:
            return
        _ = loop.cancel()
        _ = await asyncio.wait({loop})
        if not loop.cancelled() and (error := loop.exception()) is not None:
            raise error

    def _detach(self, binding: OptimizerBinding) -> None:
        if binding in self._bindings:
            self._bindings.remove(binding)
        if not self._bindings:
            self._bound.clear()
        in_flight = self._in_flight
        if in_flight is not None and in_flight[0] is binding:
            _ = in_flight[1].cancel()

    async def _run_forever(self) -> None:
        await self._optimize_roles(overdue_only=True)
        while True:
            await self._wait_for_boundary()
            await self._optimize_roles(overdue_only=False)

    async def _wait_for_boundary(self) -> None:
        while True:
            self._rescheduled.clear()
            seconds = self._seconds_until_boundary()
            logger.info(
                "[memory_optimizer] 距下次优化 %.0f 秒 (%.1f 小时)",
                seconds,
                seconds / 3600,
            )
            try:
                _ = await asyncio.wait_for(self._rescheduled.wait(), timeout=seconds)
            except TimeoutError:
                return

    def _seconds_until_boundary(self) -> float:
        """Seconds until the next multiple of the interval since the epoch."""
        now = self._now()
        now_ts = now.replace(second=0, microsecond=0).timestamp()
        next_ts = (now_ts // self._interval + 1) * self._interval
        return max(1.0, next_ts - now.timestamp())

    async def _binding(self) -> OptimizerBinding:
        while not self._bindings:
            _ = await self._bound.wait()
        active = [binding for binding in self._bindings if binding.is_active()]
        return (active or self._bindings)[-1]

    async def _optimize_roles(self, *, overdue_only: bool) -> None:
        binding = await self._binding()
        now = self._now().astimezone()
        for role in binding.roles.list_roles():
            if overdue_only and not self._is_overdue(binding, role.id, now=now):
                continue
            if overdue_only:
                logger.info("[memory_optimizer] 补跑过期角色: %s", role.id)
            await self._optimize_role(role.id)

    async def _optimize_role(self, role_id: str) -> None:
        while True:
            binding = await self._binding()
            task = asyncio.create_task(
                self._optimizer.optimize(binding.memory, binding.models, role_id),
                name=f"memory_optimizer:{role_id}",
            )
            self._in_flight = (binding, task)
            self._run = MemoryOptimizationRun(
                role_id=role_id, started_at=datetime.now().astimezone()
            )
            try:
                _ = await asyncio.wait({task})
            finally:
                if not task.done():
                    # The loop itself is cancelled (``close``).
                    _ = task.cancel()
                    _ = await asyncio.wait({task})
                self._in_flight = None
                self._run = None
            if task.cancelled() and binding not in self._bindings:
                # Its generation retired mid-run; run the role on the current one.
                continue
            if task.cancelled():
                logger.error("[memory_optimizer] 角色整理被意外取消: %s", role_id)
            elif (error := task.exception()) is not None:
                logger.error(
                    "[memory_optimizer] 角色整理失败: %s", role_id, exc_info=error
                )
            return

    def _is_overdue(
        self, binding: OptimizerBinding, role_id: str, *, now: datetime
    ) -> bool:
        documents = binding.memory.role(role_id)
        if documents is None:
            return False
        state = documents.read_state()
        # SELF.md 还没按当前写入规则重写的角色，启动时就补跑一次。
        if self_rewrite_pending(state):
            return True
        raw = str(state.get(LAST_OPTIMIZED_STATE_KEY) or "").strip()
        if not raw:
            return True
        try:
            last = datetime.fromisoformat(raw)
        except ValueError:
            return True
        if last.tzinfo is None:
            last = last.astimezone()
        return now - last >= timedelta(seconds=self._interval)
