"""The ``background`` plugin capability: plugin-scoped tasks (#901 P2).

``PluginBackground`` is the ``host.background`` core service; each plugin's
view owns the tasks it spawns and cancels them when the plugin stops.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from agent.plugin_host.core_keys import PluginBinding
from core.common.runtime_tasks import create_runtime_task


class PluginBackground:
    """The ``host.background`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> BackgroundCapability:
        """The background capability of the plugin ``binding`` describes."""
        return BackgroundCapability(binding)


class BackgroundCapability:
    """启动可取消后台任务；插件卸载时任务被取消并等待退出。"""

    def __init__(self, binding: PluginBinding) -> None:
        self._effects = binding.scope
        self._plugin_id = binding.plugin_id

    def spawn_runtime[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """Retain the current runtime until work finishes; own cancellation on unload."""
        return self._spawn(coro, name=name, retain_runtime=True)

    def spawn[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """启动作用域任务；开始卸载后拒绝启动并关闭尚未运行的协程。"""
        return self._spawn(
            coro, name=f"plugin:{self._plugin_id}:{name}", retain_runtime=False
        )

    def _spawn[T](
        self,
        coro: Coroutine[object, object, T],
        *,
        name: str,
        retain_runtime: bool,
    ) -> asyncio.Task[T]:
        try:
            self._effects.ensure_active(f"background:{name}")
            task = (
                create_runtime_task(coro, name=name)
                if retain_runtime
                else asyncio.create_task(coro, name=name)
            )
        except BaseException:
            coro.close()
            raise
        try:
            # Register at the actual spawn point to preserve LIFO ordering with
            # each task's resources, and release completed results immediately.
            release = self._effects.effect(
                lambda: self._cancel(task), f"background:{name}"
            )
        except BaseException:
            task.cancel()
            raise
        # Business errors remain with the caller or asyncio's error handler.
        task.add_done_callback(lambda _completed: release())
        return task

    @staticmethod
    async def _cancel(task: asyncio.Task[object]) -> None:
        if task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
