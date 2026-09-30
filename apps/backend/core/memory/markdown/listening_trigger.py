"""旁听整理（#541）的触发：记录入库时与定时全量检查时，在后台整理到期的群。

- 入库：发生在渠道接收里（事件循环线程上的同步调用），整理放进独立的后台任务；
  同一个群同时只有一个任务，任务运行期间又有记录入库时，结束前再检查一次。
- 定时检查：运行时启动后立即扫一遍，此后每 ``SWEEP_INTERVAL_S`` 秒一遍。只看
  游标之后还有记录的群（一次分组查询），逐个检查、到期才调模型。这样跨天后
  不再有人说话的群、关掉旁听后剩下的记录、以及失败或过期未提交的批次，都会在
  下一遍被整理，而不必等这个群的下一条消息。

整理失败只记日志，由下一次入库或下一遍定时检查重试。
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation.listening_store import GroupListeningStore, ListeningMessage

    from .listening import ListeningConsolidation

logger = logging.getLogger("memory.markdown")

# 定时全量检查的间隔（秒）。
SWEEP_INTERVAL_S = 30 * 60


def _today() -> date:
    """检查时的本地日期，跨天规则据此判断。"""
    return datetime.now().astimezone().date()


class ListeningTrigger:
    """Runs ``consolidation`` for groups in the background as records arrive
    and on a periodic sweep.

    The runtime attaches it to the listening store once built, starts the
    sweep when the runtime starts (on the event loop), and detaches it before
    draining, so a retired configuration version takes no new work.
    """

    def __init__(
        self,
        consolidation: "ListeningConsolidation",
        *,
        sweep_interval_s: float = SWEEP_INTERVAL_S,
    ) -> None:
        self._consolidation = consolidation
        self._sweep_interval_s = sweep_interval_s
        self._store: GroupListeningStore | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # 有新记录入库、需要再检查一次的群。
        self._requested: set[str] = set()
        self._sweeper: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    def attach(self, store: "GroupListeningStore") -> None:
        """Starts checking ``store``'s groups as their records are stored."""
        if self._store is not None:
            raise RuntimeError("旁听整理已接入旁听记录")
        self._store = store
        store.add_heard_listener(self.on_heard)

    def start(self) -> None:
        """Starts the periodic sweep, the first pass right away.

        Must run on the event loop thread (it creates a task).
        """
        if self._sweeper is not None:
            raise RuntimeError("旁听定时检查已启动")
        self._sweeper = contextvars.Context().run(
            asyncio.create_task, self._sweep_loop(), name="markdown-memory-listening"
        )

    def detach(self) -> None:
        """Stops taking new triggers and sweeps; running checks finish (``drain``)."""
        if self._store is not None:
            self._store.remove_heard_listener(self.on_heard)
        self._stopped.set()

    async def drain(self) -> None:
        """Waits for the sweep and running consolidations before providers close."""
        if self._sweeper is not None:
            _ = await asyncio.gather(self._sweeper, return_exceptions=True)
        while self._tasks:
            _ = await asyncio.gather(
                *tuple(self._tasks.values()), return_exceptions=True
            )
            await asyncio.sleep(0)

    def on_heard(self, message: "ListeningMessage") -> None:
        """A record was stored: checks its group in the background.

        The store calls its listeners synchronously from ``hear``, which the
        channel intake runs on the event loop thread; this creates a task, so
        it must be called there. The task runs in a fresh context, so it
        inherits no lease of the intake and cannot fail that intake.
        """
        thread_id = message.thread_id
        self._requested.add(thread_id)
        if thread_id not in self._tasks:
            self._start(thread_id)

    async def sweep(self) -> None:
        """One pass over every group with records past its cursor, in turn.

        A group already being checked by its own task is left to that task.
        A group that fails is logged and the pass goes on to the next one.
        """
        for thread_id in self._consolidation.pending_groups():
            if self._stopped.is_set():
                return
            if thread_id in self._tasks:
                continue
            try:
                _ = await self._check(thread_id)
            except Exception:
                # 后台检查的边界：一个群出错不影响其余的群，下一遍再试。
                logger.exception("listening sweep failed: thread=%s", thread_id)

    async def _sweep_loop(self) -> None:
        while not self._stopped.is_set():
            await self.sweep()
            try:
                _ = await asyncio.wait_for(
                    self._stopped.wait(), timeout=self._sweep_interval_s
                )
            except TimeoutError:
                continue

    async def _check(self, thread_id: str) -> bool:
        """整理该群到期的批次；失败时记日志并返回 False。"""
        result = await self._consolidation.consolidate(thread_id, today=_today())
        if result.trace.get("mode") != "failed":
            return True
        logger.warning(
            "listening consolidation failed: thread=%s step=%s err=%s",
            thread_id,
            result.trace.get("step"),
            result.trace.get("error"),
        )
        return False

    def _start(self, thread_id: str) -> None:
        task = contextvars.Context().run(
            asyncio.create_task,
            self._run_requested(thread_id),
            name=f"markdown-memory-listening:{thread_id}",
        )
        self._tasks[thread_id] = task
        task.add_done_callback(lambda done: self._on_done(done, thread_id))

    async def _run_requested(self, thread_id: str) -> None:
        while thread_id in self._requested:
            self._requested.discard(thread_id)
            if not await self._check(thread_id):
                # 失败后不立即重试，交给下一次入库或定时检查。
                self._requested.discard(thread_id)
                return

    def _on_done(self, task: asyncio.Task[None], thread_id: str) -> None:
        if self._tasks.get(thread_id) is task:
            _ = self._tasks.pop(thread_id)
        if task.cancelled():
            self._requested.discard(thread_id)
            return
        exc = task.exception()
        if exc is not None:
            # 后台任务的边界：记下失败，交给下一次入库或定时检查重试。
            self._requested.discard(thread_id)
            logger.warning(
                "listening consolidation crashed: thread=%s err=%r", thread_id, exc
            )
            return
        # 任务收尾与回调之间又有记录入库时，接着检查。
        if thread_id in self._requested and thread_id not in self._tasks:
            self._start(thread_id)
