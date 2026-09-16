"""Bounded request/reply rendezvous for plugin-owned renderer backgrounds."""

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent.plugin_host.bridge_events import PluginRpcError


@dataclass
class RendererRequest:
    """One caller and the exact background registration serving its request."""

    caller: str
    provider: str
    future: asyncio.Future[dict[str, Any]]


class RendererRequests:
    """Owns time-bounded requests, including cancellation when either end leaves."""

    def __init__(self) -> None:
        self.pending: dict[str, RendererRequest] = {}

    def create(self, caller: str, provider: str) -> tuple[str, RendererRequest]:
        """Admits at most 128 concurrent rendezvous without taking a bridge lane."""
        if len(self.pending) >= 128:
            raise PluginRpcError("plugin_busy", "插件后台请求过多")
        request = RendererRequest(
            caller, provider, asyncio.get_running_loop().create_future()
        )
        request_id = uuid4().hex
        self.pending[request_id] = request
        return request_id, request

    def reply(self, request_id: str, provider: str, payload: dict[str, Any]) -> None:
        """Accepts a reply only from the registration that received the request."""
        request = self.pending.get(request_id)
        if request is None or request.future.done():
            return
        if request.provider != provider:
            raise PluginRpcError("plugin_invalid_reply", "插件后台响应来源不匹配")
        error = payload.get("error")
        if isinstance(error, dict):
            request.future.set_exception(
                PluginRpcError(
                    str(error.get("code") or "plugin_handler_failed"),
                    str(error.get("message") or "插件后台执行失败"),
                )
            )
        else:
            request.future.set_result({"result": payload.get("result")})

    def cancel(self, owner: str | None = None) -> None:
        """Rejects requests for a removed endpoint or a replaced runtime generation."""
        for request_id, request in list(self.pending.items()):
            if owner is not None and owner not in (request.caller, request.provider):
                continue
            self.pending.pop(request_id)
            if not request.future.done():
                request.future.set_exception(
                    PluginRpcError("plugin_unavailable", "插件通信已停用或替换")
                )
