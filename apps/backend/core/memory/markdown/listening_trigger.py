"""旁听整理（#541）的触发：旁听记录入库时在后台检查并整理该群。

入库发生在渠道接收里（同步调用），所以整理放进独立的后台任务：同一个群同时
只有一个任务，任务运行期间又有记录入库时，任务结束前再检查一次。整理失败只
记日志，该群下一条记录入库时重试。
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation.listening_store import GroupListeningStore, ListeningMessage

    from .listening import ListeningConsolidation

logger = logging.getLogger("memory.markdown")


class ListeningTrigger:
    """Runs ``consolidation`` for a group in the background as its records arrive.

    The runtime attaches it to the listening store once built and detaches
    it before draining, so a retired configuration version takes no new work.
    """

    def __init__(self, consolidation: "ListeningConsolidation") -> None:
        self._consolidation = consolidation
        self._store: GroupListeningStore | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # 有新记录入库、需要再检查一次的群。
        self._requested: set[str] = set()

    def attach(self, store: "GroupListeningStore") -> None:
        """Starts checking ``store``'s groups as their records are stored."""
        if self._store is not None:
            raise RuntimeError("旁听整理已接入旁听记录")
        self._store = store
        store.add_heard_listener(self.on_heard)

    def detach(self) -> None:
        """Stops taking new triggers; already running consolidations finish."""
        if self._store is not None:
            self._store.remove_heard_listener(self.on_heard)

    async def drain(self) -> None:
        """Waits for the running consolidations before providers are closed."""
        while self._tasks:
            _ = await asyncio.gather(
                *tuple(self._tasks.values()), return_exceptions=True
            )
            await asyncio.sleep(0)

    def on_heard(self, message: "ListeningMessage") -> None:
        """A record was stored: checks its group in the background.

        The task runs in a fresh context, so it inherits no lease of the
        intake that stored the record and cannot fail that intake.
        """
        thread_id = message.thread_id
        self._requested.add(thread_id)
        if thread_id not in self._tasks:
            self._start(thread_id)

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
            result = await self._consolidation.consolidate(thread_id)
            if result.trace.get("mode") == "failed":
                logger.warning(
                    "listening consolidation failed: thread=%s step=%s err=%s",
                    thread_id,
                    result.trace.get("step"),
                    result.trace.get("error"),
                )
                # 失败后不立即重试，该群下一条记录入库时再来。
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
            # 后台任务的边界：记下失败，该群下一条记录入库时重试。
            self._requested.discard(thread_id)
            logger.warning(
                "listening consolidation crashed: thread=%s err=%r", thread_id, exc
            )
            return
        # 任务收尾与回调之间又有记录入库时，接着检查。
        if thread_id in self._requested and thread_id not in self._tasks:
            self._start(thread_id)
