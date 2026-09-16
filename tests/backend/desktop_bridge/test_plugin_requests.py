"""bridge 级：plugin.<id>.<method> 经现有 DesktopBridgeService.handle 路由。

覆盖验收标准 1（已注册方法可调用、未注册方法被拒 unknown_method）与
验收标准 2（插件卸载/反注册后其 RPC 方法立即不可调用）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.method_policy import Handler, MethodPolicy
from desktop_bridge.plugin_requests import DesktopPluginRequestHandler
from desktop_bridge.request_router import DesktopBridgeRequestRouter
from desktop_bridge.service import DesktopBridgeService
from desktop_bridge.request_dispatcher import BridgeRequestDispatcher
from session.manager import SessionManager


def _service(tmp_path, registry: PluginRpcRegistry | None) -> DesktopBridgeService:
    return DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
        plugin_rpc_registry=registry,
    )


def _policy(**overrides) -> MethodPolicy:
    return MethodPolicy(handler=Handler.GENERATION, **overrides)


@pytest.mark.asyncio
async def test_registered_plugin_method_is_callable_through_the_bridge(tmp_path):
    registry = PluginRpcRegistry()

    async def echo(payload):
        return {"heard": payload.get("text")}

    registry.register("plugin.demo.echo", "demo", echo, _policy())
    service = _service(tmp_path, registry)
    try:
        response = await service.handle(
            {"id": "r1", "method": "plugin.demo.echo", "payload": {"text": "hi"}},
            emit_event=lambda event: None,
        )
        assert response.error is None
        assert response.payload == {"heard": "hi"}
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_unregistered_plugin_method_is_rejected_as_unknown_method(tmp_path):
    registry = PluginRpcRegistry()
    service = _service(tmp_path, registry)
    try:
        response = await service.handle(
            {"id": "r2", "method": "plugin.demo.missing", "payload": {}},
            emit_event=lambda event: None,
        )
        assert response.error is not None
        assert response.error.code == "unknown_method"
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_a_method_never_registered_by_any_plugin_is_also_unknown(tmp_path):
    # 没有任何 PluginRpcRegistry（例如插件系统未启用）时同样必须安全退化
    service = _service(tmp_path, None)
    try:
        response = await service.handle(
            {"id": "r3", "method": "plugin.demo.echo", "payload": {}},
            emit_event=lambda event: None,
        )
        assert response.error is not None
        assert response.error.code == "unknown_method"
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_unregistering_a_method_makes_it_immediately_uncallable(tmp_path):
    registry = PluginRpcRegistry()

    async def echo(payload):
        return {"ok": True}

    registry.register("plugin.demo.echo", "demo", echo, _policy())
    service = _service(tmp_path, registry)
    try:
        first = await service.handle(
            {"id": "r4", "method": "plugin.demo.echo", "payload": {}},
            emit_event=lambda event: None,
        )
        assert first.error is None

        # 模拟插件卸载：RPC capability 的 dispose 会调用 unregister
        registry.unregister("plugin.demo.echo")

        second = await service.handle(
            {"id": "r5", "method": "plugin.demo.echo", "payload": {}},
            emit_event=lambda event: None,
        )
        assert second.error is not None
        assert second.error.code == "unknown_method"
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_plugin_config_methods_are_never_routed_to_the_generic_rpc_handler(
    tmp_path,
):
    # plugin.config.* 由 ReloadableDesktopService 专用分支处理；裸 DesktopBridgeService
    # （没有 AppRuntime/settings 事务）必须像 runtime.* 一样退化为 unknown_method
    registry = PluginRpcRegistry()

    async def get_config(payload):
        pytest.fail("plugin.config.get must never reach the generic RPC handler")

    registry.register("plugin.config.get", "config", get_config, _policy())
    service = _service(tmp_path, registry)
    try:
        response = await service.handle(
            {
                "id": "r6",
                "method": "plugin.config.get",
                "payload": {"plugin_id": "demo"},
            },
            emit_event=lambda event: None,
        )
        assert response.error is not None
        assert response.error.code == "unknown_method"
    finally:
        await service.aclose()


def _router(*, registry: PluginRpcRegistry | None) -> DesktopBridgeRequestRouter:
    from unittest.mock import AsyncMock

    return DesktopBridgeRequestRouter(
        roles=SimpleNamespace(handle=AsyncMock(return_value=None)),
        sessions_and_tasks=SimpleNamespace(handle=AsyncMock(return_value=None)),
        chat=SimpleNamespace(handle=AsyncMock(return_value=None)),
        voice=SimpleNamespace(handle=AsyncMock(return_value=None)),
        plugins=DesktopPluginRequestHandler(registry),
    )


@pytest.mark.asyncio
async def test_router_stops_at_the_plugin_handler_without_reaching_domain_handlers():
    registry = PluginRpcRegistry()

    async def handler(payload):
        return {"result": "from-plugin"}

    registry.register("plugin.demo.run", "demo", handler, _policy())
    router = _router(registry=registry)

    result = await router.dispatch(
        "plugin.demo.run",
        {},
        request_id="req",
        emit_event=lambda event: None,
    )

    assert result == {"result": "from-plugin"}
    router._roles.handle.assert_not_awaited()
    router._chat.handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_falls_through_for_unregistered_plugin_methods():
    router = _router(registry=PluginRpcRegistry())

    result = await router.dispatch(
        "plugin.demo.missing",
        {},
        request_id="req",
        emit_event=lambda event: None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_background_callback_can_call_backend_at_dispatcher_capacity_one(
    tmp_path,
):
    registry = PluginRpcRegistry()
    service = _service(tmp_path, registry)
    registry.communication.configure(
        lambda plugin_id: () if plugin_id == "demo" else None, service.event_bus
    )
    dispatcher = BridgeRequestDispatcher(
        max_concurrency=1, policy_resolver=service.resolve_method_policy
    )

    async def echo(payload):
        return {"heard": payload["text"]}

    registry.register("plugin.demo.echo", "demo", echo, _policy())
    token = registry.communication.generation
    provider = {"plugin_id": "demo", "owner": "background", "generation": token}
    await registry.communication.handle("open", provider)
    await registry.communication.handle("register", {**provider, "name": "sync"})

    async def request(method, payload):
        result = asyncio.get_running_loop().create_future()

        async def run():
            response = await service.handle(
                {"id": "test", "method": method, "payload": payload},
                emit_event=lambda event: None,
            )
            result.set_result(response)

        dispatcher.submit({"method": method}, run)
        return await result

    tasks = []

    async def callback(event):
        response = await request("plugin.demo.echo", {"text": "round trip"})
        assert response.error is None
        await request(
            "plugins.communication.reply",
            {
                **provider,
                "request_id": event["payload"]["request_id"],
                "result": response.payload,
            },
        )

    def emit(event):
        tasks.append(asyncio.create_task(callback(event)))

    service.add_event_listener(emit)
    try:
        # More pending rendezvous than the semaphore limit proves neither
        # callback backend work nor replies are starved by waiting callers.
        responses = await asyncio.wait_for(
            asyncio.gather(
                *[
                    request(
                        "plugins.communication.call",
                        {
                            "plugin_id": "demo",
                            "owner": f"ui-{index}",
                            "generation": token,
                            "name": "sync",
                        },
                    )
                    for index in range(12)
                ]
            ),
            timeout=3,
        )
        assert all(response.error is None for response in responses)
        assert all(
            response.payload == {"result": {"heard": "round trip"}}
            for response in responses
        )
        await asyncio.gather(*tasks)
    finally:
        await dispatcher.aclose(cancel=True)
        await service.aclose()


@pytest.mark.asyncio
async def test_disabled_peer_returns_unavailable_before_method_lookup(tmp_path):
    registry = PluginRpcRegistry()
    registry.communication.configure(
        lambda plugin_id: ("missing",) if plugin_id == "demo" else None, EventBus()
    )
    service = _service(tmp_path, registry)
    try:
        response = await service.handle(
            {
                "id": "missing",
                "method": "plugin.missing.echo",
                "payload": {
                    "__plugin_context": {
                        "plugin_id": "demo",
                        "generation": registry.communication.generation,
                    },
                },
            },
            emit_event=lambda event: None,
        )
        assert response.error is not None
        assert response.error.code == "plugin_unavailable"
    finally:
        await service.aclose()
