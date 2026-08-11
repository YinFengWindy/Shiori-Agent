from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from desktop_bridge.plugin_package_requests import DesktopPluginPackageRequestHandler


@pytest.mark.asyncio
async def test_plugin_package_handler_routes_catalog_and_install() -> None:
    installed = SimpleNamespace(to_dict=Mock(return_value={"plugin_id": "desktop-pet"}))
    service = SimpleNamespace(
        catalog=AsyncMock(return_value=[{"repository": "Shiori-Plugins/desktop-pet"}]),
        installed=Mock(return_value=[]),
        install=AsyncMock(return_value=installed),
        uninstall=Mock(return_value=True),
    )
    handler = DesktopPluginPackageRequestHandler(service)

    catalog = await handler.handle("plugins.catalog", {})
    result = await handler.handle(
        "plugins.install",
        {"repository": "desktop-pet"},
    )

    assert catalog == {"plugins": [{"repository": "Shiori-Plugins/desktop-pet"}]}
    assert result == {"plugin": {"plugin_id": "desktop-pet"}}
    service.install.assert_awaited_once_with("desktop-pet")


@pytest.mark.asyncio
async def test_plugin_package_handler_preserves_or_purges_data_explicitly() -> None:
    service = SimpleNamespace(uninstall=Mock(return_value=True))
    handler = DesktopPluginPackageRequestHandler(service)

    result = await handler.handle(
        "plugins.uninstall",
        {"plugin_id": "desktop-pet", "purge_data": True},
    )

    assert result == {"removed": True}
    service.uninstall.assert_called_once_with("desktop-pet", purge_data=True)


@pytest.mark.asyncio
async def test_plugin_package_handler_rejects_invalid_mutation_payloads() -> None:
    handler = DesktopPluginPackageRequestHandler(SimpleNamespace())

    with pytest.raises(ValueError, match="repository"):
        await handler.handle("plugins.install", {})
    with pytest.raises(ValueError, match="purge_data"):
        await handler.handle(
            "plugins.uninstall",
            {"plugin_id": "desktop-pet", "purge_data": "yes"},
        )


@pytest.mark.asyncio
async def test_plugin_package_handler_coordinates_runtime_enable_disable_and_rpc() -> (
    None
):
    service = SimpleNamespace(
        set_enabled=Mock(
            side_effect=lambda plugin_id, enabled: {
                "plugin_id": plugin_id,
                "enabled": enabled,
            }
        ),
    )
    runtime = SimpleNamespace(
        start=AsyncMock(return_value=True),
        stop=AsyncMock(return_value=True),
        call_rpc=AsyncMock(return_value="ready"),
    )
    handler = DesktopPluginPackageRequestHandler(service, runtime)

    enabled = await handler.handle("plugins.enable", {"plugin_id": "desktop-pet"})
    rpc = await handler.handle(
        "plugins.rpc",
        {
            "plugin_id": "desktop-pet",
            "method": "pet.state",
            "payload": {"role_id": "r1"},
        },
    )
    disabled = await handler.handle("plugins.disable", {"plugin_id": "desktop-pet"})

    assert enabled == {"plugin": {"plugin_id": "desktop-pet", "enabled": True}}
    assert rpc == {"result": "ready"}
    assert disabled == {"plugin": {"plugin_id": "desktop-pet", "enabled": False}}
    runtime.start.assert_awaited_once_with("desktop-pet")
    runtime.call_rpc.assert_awaited_once_with(
        "desktop-pet", "pet.state", {"role_id": "r1"}
    )
    runtime.stop.assert_awaited_once_with("desktop-pet")


@pytest.mark.asyncio
async def test_plugin_enable_rolls_back_when_runtime_start_fails() -> None:
    service = SimpleNamespace(
        set_enabled=Mock(
            side_effect=lambda plugin_id, enabled: {
                "plugin_id": plugin_id,
                "enabled": enabled,
            }
        ),
    )
    runtime = SimpleNamespace(start=AsyncMock(side_effect=RuntimeError("boom")))
    handler = DesktopPluginPackageRequestHandler(service, runtime)

    with pytest.raises(RuntimeError, match="boom"):
        await handler.handle("plugins.enable", {"plugin_id": "desktop-pet"})

    assert service.set_enabled.call_args_list == [
        (("desktop-pet", True),),
        (("desktop-pet", False),),
    ]
