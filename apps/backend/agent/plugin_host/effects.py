"""可回滚副作用登记：卸载先停止事件订阅，再逆序处置其余资源。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

Dispose = Callable[[], Awaitable[None] | None]


@dataclass
class Effect:
    """单条已登记副作用：label 用于诊断，dispose 负责撤销。"""

    label: str
    dispose: Dispose
    is_subscription: bool = False


class EffectScope:
    """插件副作用作用域：先关闭准入和退订事件，再 LIFO 清理其余资源。"""

    def __init__(self, owner: str) -> None:
        self._owner = owner
        self._effects: list[Effect] = []
        self._closing = False
        self._dispose_lock = asyncio.Lock()

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def labels(self) -> list[str]:
        """Returns registration labels in registration order, for diagnostics."""
        return [effect.label for effect in self._effects]

    @property
    def active(self) -> bool:
        """Whether subscriptions and new resource registrations can accept work."""
        return not self._closing

    def ensure_active(self, label: str) -> None:
        """Reject registration before the caller acquires any underlying resource."""
        if self._closing:
            raise RuntimeError(f"EffectScope({self._owner}) 已处置，拒绝登记: {label}")

    def add(self, label: str, dispose: Dispose) -> None:
        """Register a resource disposer, run in LIFO order after event unsubscription."""
        self.ensure_active(label)
        self._effects.append(Effect(label=label, dispose=dispose))

    def add_subscription(self, label: str, dispose: Dispose) -> None:
        """Host-only subscription registration; no plugin-defined cleanup priorities."""
        self.ensure_active(label)
        self._effects.append(Effect(label, dispose, is_subscription=True))

    async def dispose_all(self) -> list[Exception]:
        """先拒绝新工作、退订，再 LIFO 清理其余 effect；失败汇总且继续清理。"""
        # 在第一次 await 之前关闭准入，连已被总线快照选中的订阅也不能再起新工作。
        self._closing = True
        # 并发调用等待现有清理；若调用者取消清理，后续调用仍可处理剩余 effect。
        async with self._dispose_lock:
            subscriptions = [e for e in self._effects if e.is_subscription]
            resources = [e for e in self._effects if not e.is_subscription]
            self._effects = resources + subscriptions
            errors: list[Exception] = []
            while self._effects:
                effect = self._effects.pop()
                try:
                    result = effect.dispose()
                    if inspect.isawaitable(result):
                        await result
                except Exception as e:
                    logger.warning(
                        "插件副作用清理失败 (%s / %s): %s", self._owner, effect.label, e
                    )
                    errors.append(e)
            return errors
