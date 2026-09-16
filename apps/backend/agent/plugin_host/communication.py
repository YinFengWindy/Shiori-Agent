"""Cooperative plugin communication using the kernel's manifest and RPC owners."""

import asyncio
import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agent.plugin_host.bridge_events import PluginBridgeEvent, PluginRpcError
from agent.plugin_host.renderer_requests import RendererRequests


def communication_name(value: Any) -> str:
    """Accepts a local method/event name, never a global plugin namespace."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-zA-Z][\w]*(?:\.[\w]+)*", value
    ):
        raise PluginRpcError("plugin_invalid_name", "插件方法或事件名称无效")
    if value.startswith("plugin."):
        raise PluginRpcError("plugin_invalid_name", "请使用插件内的局部名称")
    return value


class PluginCommunication:
    """Routes declared peers and backgrounds within one active kernel generation.

    The resolver reads existing PluginHandles; this is not a second dependency
    registry and never enables a missing provider. IDs are cooperation metadata,
    not authentication in the shared-process trust model.
    """

    def __init__(self, registry: object) -> None:
        self.generation = uuid4().hex
        self._registry = registry
        self._resolve: Callable[[str], tuple[str, ...] | None] = lambda _id: None
        self._event_bus: Any = None
        self._active = True
        self._owners: dict[str, str] = {}
        self._renderers: dict[str, str] = {}
        self._handlers: dict[tuple[str, str], str] = {}
        self._requests = RendererRequests()

    def configure(
        self, resolve: Callable[[str], tuple[str, ...] | None], event_bus: Any
    ) -> None:
        """Binds authoritative active-plugin declarations supplied by the kernel."""
        self._resolve, self._event_bus = resolve, event_bus

    def authorize(self, caller: str, target: str, generation: str) -> bool:
        """Checks caller lifetime and declared ownership without activating targets."""
        if not self._active or generation != self.generation:
            raise PluginRpcError("plugin_unavailable", "插件运行代际已替换")
        declared = self._resolve(caller)
        if declared is None:
            raise PluginRpcError("plugin_unavailable", f"插件 {caller} 不可用")
        if target != caller and target not in declared:
            raise PluginRpcError(
                "plugin_dependency_undeclared", f"未声明插件依赖: {target}"
            )
        return self._resolve(target) is not None

    async def handle(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Handles transport operations independently of plugin backend RPC policies."""
        if operation == "disconnect":
            renderer = str(payload.get("renderer") or "")
            for context_owner, context_renderer in list(self._renderers.items()):
                if context_renderer == renderer:
                    self.remove_owner(context_owner)
            return {}
        caller = str(payload.get("plugin_id") or "")
        owner = str(payload.get("owner") or "")
        generation = str(payload.get("generation") or "")
        if operation == "open":
            self.authorize(caller, caller, self.generation)
            if not owner:
                raise PluginRpcError("plugin_invalid_request", "插件通信缺少调用方标识")
            self._owners[owner] = caller
            self._renderers[owner] = str(payload.get("renderer") or "")
            return {"generation": self.generation}
        if operation == "close":
            # Late disposers from retired contexts must not remove new handlers.
            if generation == self.generation:
                self.remove_owner(owner)
            return {}
        target = str(payload.get("target") or caller)
        available = self.authorize(caller, target, generation)
        if operation == "resolve":
            return {"available": available}
        if not available:
            raise PluginRpcError("plugin_unavailable", f"插件 {target} 不可用")
        if not owner:
            raise PluginRpcError("plugin_invalid_request", "插件通信缺少调用方标识")
        if operation == "reply":
            self._requests.reply(str(payload.get("request_id") or ""), owner, payload)
            return {}
        name = communication_name(payload.get("name"))
        if operation == "register":
            key = (caller, name)
            if key in self._handlers:
                raise PluginRpcError(
                    "plugin_method_exists", f"插件后台方法已注册: {name}"
                )
            self._handlers[key] = owner
            return {}
        if operation == "call":
            return await self._call(caller, target, owner, name, payload)
        raise PluginRpcError("plugin_invalid_request", "未知插件通信操作")

    async def _call(
        self, caller: str, target: str, owner: str, name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        provider = self._handlers.get((target, name))
        if provider is None:
            raise PluginRpcError(
                "plugin_unavailable", f"插件后台方法不可用: {target}.{name}"
            )
        arguments = payload.get("payload") or {}
        if not isinstance(arguments, dict):
            raise PluginRpcError("plugin_invalid_request", "插件后台参数必须是对象")
        request_id, request = self._requests.create(owner, provider)
        try:
            event = PluginBridgeEvent(
                f"plugin.{target}.__request",
                {
                    "owner": provider,
                    "request_id": request_id,
                    "name": name,
                    "payload": arguments,
                    "caller": caller,
                },
                self._registry,
            )
            await self._event_bus.emit(event)
            if not event.dispatched:
                raise PluginRpcError("plugin_unavailable", "插件渲染进程传输不可用")
            try:
                return await asyncio.wait_for(request.future, timeout=15)
            except TimeoutError as error:
                raise PluginRpcError("plugin_timeout", "插件后台响应超时") from error
        finally:
            self._requests.pending.pop(request_id, None)
            if not request.future.done():
                request.future.cancel()
            elif not request.future.cancelled():
                # Transport failure may win the race with owner retirement.
                _ = request.future.exception()

    def remove_owner(self, owner: str) -> None:
        """Unregisters one context and cancels calls owned by either side of it."""
        self._owners.pop(owner, None)
        self._renderers.pop(owner, None)
        self._handlers = {
            key: value for key, value in self._handlers.items() if value != owner
        }
        self._requests.cancel(owner)

    def remove_plugin(self, plugin_id: str) -> None:
        """Reclaims registrations when plugin setup fails or its scope is disposed."""
        for owner, target in list(self._owners.items()):
            if target == plugin_id:
                self.remove_owner(owner)

    def retire(self) -> None:
        """Ends renderer rendezvous immediately; ordinary leased chat can still drain."""
        self._active = False
        self._handlers.clear()
        self._owners.clear()
        self._renderers.clear()
        self._requests.cancel()
