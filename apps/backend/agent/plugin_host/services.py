"""Scoped public plugin contracts, independent of domain and static peer dependencies."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.services import ServiceHandler
from agent.plugin_host.effects import EffectScope


def _name(value: str) -> str:
    if not value or value != value.strip() or len(value) > 128:
        raise ValueError("服务标识不能为空、包含首尾空白或超过 128 字符")
    return value


@dataclass(frozen=True)
class _Service:
    descriptor: dict[str, object]
    methods: dict[str, ServiceHandler]
    scope: EffectScope


class PluginServiceRegistry:
    """Resolve only explicit, active registrations; never activate or select providers."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Service] = {}

    def register(
        self,
        plugin_id: str,
        service_id: str,
        *,
        contract: str,
        label: str,
        methods: Mapping[str, ServiceHandler],
        metadata: Mapping[str, object] | None,
        scope: EffectScope,
    ) -> None:
        """Capture published methods and metadata for this precise plugin instance."""
        scope.ensure_active("service:register")
        key = (plugin_id, _name(service_id))
        if key in self._entries:
            raise ValueError(f"插件服务已注册: {plugin_id}.{service_id}")
        if not methods or any(not callable(handler) for handler in methods.values()):
            raise ValueError("插件服务必须公开可调用的方法")
        public_methods = {_name(name): handler for name, handler in methods.items()}
        descriptor = {
            "plugin_id": plugin_id,
            "service_id": service_id,
            "contract": _name(contract),
            "label": _name(label),
            "metadata": dict(metadata or {}),
        }
        # JSON is the public boundary; non-finite numbers and implementation objects
        # cannot leak into another plugin or a renderer through metadata.
        descriptor = json.loads(json.dumps(descriptor, allow_nan=False))
        entry = _Service(descriptor, public_methods, scope)
        self._entries[key] = entry

        def remove() -> None:
            if self._entries.get(key) is entry:
                self._entries.pop(key)

        scope.add(f"service:{service_id}", remove)

    def list(self, contract: str) -> list[dict[str, object]]:
        """Return detached public descriptors for one exact contract."""
        return [
            json.loads(json.dumps(entry.descriptor))
            for entry in self._entries.values()
            if entry.scope.active and entry.descriptor["contract"] == _name(contract)
        ]

    async def call(
        self,
        plugin_id: str,
        service_id: str,
        name: str,
        payload: dict[str, object],
        *,
        caller_active: Callable[[], bool],
    ) -> dict[str, object]:
        """Call a published method and reject results from retired owners or providers."""
        key = (plugin_id, service_id)
        entry = self._entries.get(key)
        if entry is None or not entry.scope.active:
            raise PluginRpcError(
                "plugin_service_unavailable",
                f"插件服务不可用: {plugin_id}.{service_id}",
            )
        method = entry.methods.get(name)
        if method is None:
            raise PluginRpcError(
                "plugin_service_method_unavailable", f"插件服务未公开方法: {name}"
            )
        result = await method(payload)
        if (
            not caller_active()
            or not entry.scope.active
            or self._entries.get(key) is not entry
        ):
            raise PluginRpcError("plugin_service_unavailable", "插件服务或调用方已停用")
        if not isinstance(result, dict):
            raise TypeError("插件服务返回值必须是 JSON 对象")
        return json.loads(json.dumps(result, allow_nan=False))


class ScopedPluginServices:
    """Bind publication to the real setup owner and its disposal scope."""

    def __init__(
        self, registry: PluginServiceRegistry, plugin_id: str, scope: EffectScope
    ):
        self._registry, self._plugin_id, self._scope = registry, plugin_id, scope

    def register(
        self,
        service_id: str,
        *,
        contract: str,
        label: str,
        methods: Mapping[str, ServiceHandler],
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Publish one service until this exact plugin instance is unloaded."""
        self._registry.register(
            self._plugin_id,
            service_id,
            contract=contract,
            label=label,
            methods=methods,
            metadata=metadata,
            scope=self._scope,
        )
