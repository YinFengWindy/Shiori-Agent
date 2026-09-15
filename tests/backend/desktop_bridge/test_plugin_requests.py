"""bridge 级：plugin.<id>.<method> 经现有 DesktopBridgeService.handle 路由。

覆盖验收标准 1（已注册方法可调用、未注册方法被拒 unknown_method）与
验收标准 2（插件卸载/反注册后其 RPC 方法立即不可调用）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.method_policy import Handler, MethodPolicy
from desktop_bridge.plugin_requests import DesktopPluginRequestHandler
from desktop_bridge.request_router import DesktopBridgeRequestRouter
from desktop_bridge.service import DesktopBridgeService
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
