"""host_service_requirements.py 行为：能力到宿主服务的映射与 setup 前预检。"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
from shiori_sdk import HostServiceUnavailable
from shiori_sdk.runtime import KNOWN_CAPABILITIES

from agent.plugin_host import HostServices
from agent.plugin_host.host_service_requirements import (
    CAPABILITY_HOST_SERVICES,
    provided_service,
    require_host_services,
)
from bus.event_bus import EventBus


def test_mapping_names_only_known_capabilities_and_real_host_services():
    """表里的键必须是 manifest 可声明的能力，值必须是 HostServices 真实字段。"""
    service_fields = {field.name for field in fields(HostServices)}
    assert set(CAPABILITY_HOST_SERVICES) <= KNOWN_CAPABILITIES
    for capability, services in CAPABILITY_HOST_SERVICES.items():
        assert services, capability
        assert set(services) <= service_fields, capability


def test_require_names_only_the_missing_services(tmp_path: Path):
    services = HostServices(event_bus=EventBus(), workspace=tmp_path)
    with pytest.raises(HostServiceUnavailable) as excinfo:
        require_host_services("demo", ["memory"], services)
    message = str(excinfo.value)
    assert "插件 demo 声明了 capability 'memory'" in message
    assert message.endswith("宿主未提供服务 role_store")


def test_require_ignores_capabilities_without_host_services():
    """未登记的能力（如 memory_engine：记忆关闭时为 None 合法）不做预检。"""
    require_host_services(
        "demo", ["events", "memory_engine"], HostServices(event_bus=EventBus())
    )


def test_provided_service_narrows_or_raises_with_all_listed_services(tmp_path: Path):
    assert provided_service("demo", "kv", tmp_path) == tmp_path
    with pytest.raises(
        HostServiceUnavailable, match="宿主未提供服务 session_manager、workspace"
    ):
        provided_service("demo", "sessions", None)
