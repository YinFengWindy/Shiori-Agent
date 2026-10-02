"""Which host services back each manifest capability, checked before plugin setup."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from shiori_sdk.runtime import HostServiceUnavailable

# capability -> 支撑它的 HostServices 字段。manifest 声明了 capability 而宿主缺少
# 其中任一服务时，setup 前就以 HostServiceUnavailable 失败，而不是让插件拿到
# None 或误报“插件未申请能力”。memory_engine 不在表内：配置关闭记忆时宿主本就
# 没有引擎，None 是合法状态而非缺失服务。
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
    "role_runtime_registry": ("role_runtime_registry",),
    "models": ("role_runtime_registry",),
    "light_provider": ("light_provider",),
    "http": ("http",),
}


def host_service_unavailable(
    plugin_id: str, capability: str, service: str
) -> HostServiceUnavailable:
    """Builds the error for a declared capability whose host service is missing."""
    return HostServiceUnavailable(
        f"插件 {plugin_id} 声明了 capability {capability!r}，"
        f"但宿主未提供服务 {service}"
    )


def require_host_services(
    plugin_id: str,
    capabilities: Iterable[str],
    provided: Mapping[str, object | None],
) -> None:
    """Fails fast when a declared capability's host service is absent.

    ``provided`` maps every service name in ``CAPABILITY_HOST_SERVICES`` to the
    host's instance (``None`` when the host was assembled without it).
    """
    for capability in capabilities:
        for service in CAPABILITY_HOST_SERVICES.get(capability, ()):
            if provided[service] is None:
                raise host_service_unavailable(plugin_id, capability, service)
