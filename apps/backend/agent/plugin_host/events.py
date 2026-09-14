"""作用域事件总线：拦截订阅并登记为 effect，修复插件直接 on() 后卸载不解绑的缺陷。"""

from __future__ import annotations

import inspect
from typing import Any

from agent.plugin_host.effects import EffectScope
from bus.event_bus import EventBus


class _Subscription:
    def __init__(self, event_type: type, handler: Any, effects: EffectScope) -> None:
        self.event_type = event_type
        self.handler = handler
        self._effects = effects
        self.active = True

    async def __call__(self, event: Any) -> Any:
        # EventBus 的 emit/observe/fanout 可能已保存旧 handler 列表；退订之外还需准入门。
        if not self.active or not self._effects.active:
            return None
        result = self.handler(event)
        return await result if inspect.isawaitable(result) else result


class ScopedEventBus:
    """插件视角的事件总线代理。

    on/off 被拦截并登记进 EffectScope，卸载先停止接收事件、统一解绑，
    再清理其它 effect；已开始执行的 handler 由插件自己的资源清理等待或取消。
    其余方法（emit/observe/fanout/enqueue 等）原样委托真实 EventBus。
    """

    def __init__(self, bus: EventBus, effects: EffectScope) -> None:
        self._bus = bus
        self._effects = effects
        self._subscriptions: list[_Subscription] = []

    def on(self, event_type: type, handler: Any) -> None:
        """登记订阅；卸载时先退订再 LIFO 清理 ctx.effect，与登记先后无关。

        作用域一旦开始清理，拒绝新订阅并跳过尚未开始的 handler；已运行的
        handler 不会被强制取消，插件仍负责在自己的 disposer 中收敛资源。
        """
        label = f"event:{getattr(event_type, '__name__', event_type)}"
        self._effects.ensure_active(label)
        subscription = _Subscription(event_type, handler, self._effects)
        self._bus.on(event_type, subscription)
        self._subscriptions.append(subscription)
        self._effects.add_subscription(label, lambda: self._unsubscribe(subscription))

    def off(self, event_type: type, handler: Any) -> None:
        """按原 handler 身份移除全部匹配订阅；重复退订安全。"""
        for subscription in tuple(self._subscriptions):
            if (
                subscription.event_type is event_type
                and subscription.handler is handler
            ):
                self._unsubscribe(subscription)

    def _unsubscribe(self, subscription: _Subscription) -> None:
        subscription.active = False
        self._bus.off(subscription.event_type, subscription)
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bus, name)
