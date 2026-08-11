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
