"""PluginRpcRegistry：注册/解析/重复注册报错/卸载后消失/策略声明。"""

from __future__ import annotations

import pytest

from agent.plugin_host.rpc import PluginRpcRegistry
from desktop_bridge.method_policy import Handler, MethodPolicy
from shiori_sdk.rpc import Concurrency


async def _echo(payload):
    return {"echo": payload}


def _policy(**overrides) -> MethodPolicy:
    return MethodPolicy(handler=Handler.GENERATION, **overrides)


def test_register_then_resolve_returns_owner_and_handler():
    registry = PluginRpcRegistry()

    registry.register("plugin.demo.ping", "demo", _echo, _policy())

    resolved = registry.resolve("plugin.demo.ping")
    assert resolved is not None
    plugin_id, handler = resolved
    assert plugin_id == "demo"
    assert handler is _echo
    assert "plugin.demo.ping" in registry


def test_unregistered_method_resolves_to_none():
    registry = PluginRpcRegistry()

    assert registry.resolve("plugin.demo.ping") is None
    assert registry.policy_for("plugin.demo.ping") is None
    assert "plugin.demo.ping" not in registry


def test_duplicate_registration_raises():
    registry = PluginRpcRegistry()
    registry.register("plugin.demo.ping", "demo", _echo, _policy())

    with pytest.raises(ValueError, match="已注册"):
        registry.register("plugin.demo.ping", "demo", _echo, _policy())


def test_unregister_is_idempotent_and_removes_method():
    registry = PluginRpcRegistry()
    registry.register("plugin.demo.ping", "demo", _echo, _policy())

    registry.unregister("plugin.demo.ping")
    assert registry.resolve("plugin.demo.ping") is None
    # 卸载后其方法立即不可调用；重复卸载不得报错
    registry.unregister("plugin.demo.ping")


def test_unregistering_one_method_does_not_affect_another_plugins_method():
    registry = PluginRpcRegistry()
    registry.register("plugin.demo.ping", "demo", _echo, _policy())
    registry.register("plugin.other.ping", "other", _echo, _policy())

    registry.unregister("plugin.demo.ping")

    assert registry.resolve("plugin.demo.ping") is None
    assert registry.resolve("plugin.other.ping") is not None


def test_policy_for_returns_the_declared_admission_and_concurrency():
    registry = PluginRpcRegistry()
    declared = _policy(concurrency=Concurrency.READ_ONLY, admission_exempt=True)
    registry.register("plugin.demo.status", "demo", _echo, declared)

    policy = registry.policy_for("plugin.demo.status")

    assert policy is declared
    assert policy.concurrency is Concurrency.READ_ONLY
    assert policy.admission_exempt is True
    assert policy.handler is Handler.GENERATION
