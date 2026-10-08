"""Which host services back each manifest capability, checked before plugin setup."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from shiori_sdk.runtime import HostServiceUnavailable

# capability -> 支撑它的 HostServices 字段名。manifest 声明了 capability 而宿主缺少
# 其中任一服务时，setup 前就以 HostServiceUnavailable 失败，而不是让插件拿到
# None 或误报“插件未申请能力”。内核预检与运行时上下文属性都只从这里取服务名。
# memory_engine 不在表内：配置关闭记忆时宿主本就没有引擎，None 是合法状态。
# role_store / workspace / session_manager / role_runtime_registry 这几项是
# 直传型 capability，经旧上下文的 __getattr__ 原样交给插件，同样必须预检。
CAPABILITY_HOST_SERVICES: Mapping[str, tuple[str, ...]] = {
    "tools": ("tool_registry",),
    "workspace": ("workspace",),
    "kv": ("workspace",),
    "role_store": ("role_store",),
    "roles": ("role_store",),
    "accounts": ("role_store",),
    "avatars": ("role_store",),
    "memory": ("workspace", "role_store"),
    "session_manager": ("session_manager",),
    "sessions": ("session_manager", "workspace"),
    "external_turns": ("external_turns",),
    "role_runtime_registry": ("role_runtime_registry",),
    "models": ("role_runtime_registry",),
    "light_provider": ("light_provider",),
    "light_model": ("light_model",),
    "scene_observations": ("scene_observations",),
    "http": ("http",),
}


def provided_service[T](plugin_id: str, capability: str, value: T | None) -> T:
    """Returns a declared capability's backing value, or raises the shared error.

    Narrows ``value`` for callers that already passed ``require_host_services``;
    the message names every service listed for ``capability``.
    """
    if value is None:
        raise HostServiceUnavailable.for_capability(
            plugin_id, capability, CAPABILITY_HOST_SERVICES[capability]
        )
    return value


def require_host_services(
    plugin_id: str, capabilities: Iterable[str], services: object
) -> None:
    """Fails fast when a declared capability's host service is absent.

    ``services`` is the kernel's ``HostServices``; each service name in
    ``CAPABILITY_HOST_SERVICES`` is read as the attribute of the same name, so
    adding a row needs no second list to keep in sync. The error names only
    the services that are actually missing.
    """
    for capability in capabilities:
        missing = [
            service
            for service in CAPABILITY_HOST_SERVICES.get(capability, ())
            if getattr(services, service) is None
        ]
        if missing:
            raise HostServiceUnavailable.for_capability(plugin_id, capability, missing)
