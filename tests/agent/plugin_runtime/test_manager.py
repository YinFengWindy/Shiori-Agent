from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent.mcp.client import McpToolInfo
from agent.plugin_packages import InstalledPlugin, PluginManifest
from agent.plugin_runtime import PluginRuntimeManager
from agent.tools.registry import ToolRegistry


def _manifest() -> PluginManifest:
    return PluginManifest.from_mapping(
        {
            "schema_version": 1,
            "plugin_id": "desktop-pet",
            "name": "Desktop Pet",
            "description": "Desktop overlay pet",
            "version": "1.0.0",
            "plugin_api_version": 1,
            "platforms": [{"os": "win32", "arch": "x64"}],
            "entrypoints": {"backend": "backend/main.py"},
            "capabilities": ["agent.tool", "plugin.rpc"],
            "permissions": ["plugin.storage"],
            "tools": [
                {
                    "remote_name": "pet_action",
                    "name": "pet_action",
                    "risk": "external-side-effect",
                    "always_on": True,
                    "search_hint": "desktop pet action",
                }
            ],
            "rpc_methods": [
                {"method": "pet.state", "remote_name": "pet_state"},
            ],
            "release": {
                "asset": "desktop-pet.zip",
                "checksums_asset": "checksums.json",
            },
        },
        source="test",
    )


class FakeInstaller:
    def __init__(self, installed: InstalledPlugin) -> None:
        self._installed = installed

    def list_installed(self) -> list[InstalledPlugin]:
        return [self._installed]


class FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.disconnected = False
        self.exited = asyncio.Event()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.tools = [
            McpToolInfo(
                name="pet_action",
                description="Move the desktop pet",
                input_schema={
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                },
            ),
            McpToolInfo(
                name="undeclared_tool",
                description="Must stay hidden",
                input_schema={"type": "object", "properties": {}},
            ),
            McpToolInfo(
                name="pet_state",
                description="Read plugin state",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    async def connect(self) -> list[McpToolInfo]:
        return self.tools

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return "ok"

    async def disconnect(self) -> None:
        self.disconnected = True
        self.exited.set()

    async def wait_until_exit(self) -> int:
        await self.exited.wait()
        return 9


def _installed(tmp_path: Path, *, enabled: bool = True) -> InstalledPlugin:
    package_dir = tmp_path / "plugins" / "desktop-pet" / "versions" / "1.0.0"
    backend = package_dir / "backend" / "main.py"
    backend.parent.mkdir(parents=True)
    backend.write_text("print('plugin')", encoding="utf-8")
    return InstalledPlugin(
        plugin_id="desktop-pet",
        version="1.0.0",
        package_dir=package_dir,
        manifest=_manifest(),
        enabled=enabled,
    )


@pytest.mark.asyncio
async def test_runtime_registers_only_manifest_allowlisted_tools(
    tmp_path: Path,
) -> None:
    registry = ToolRegistry()
    clients: list[FakeClient] = []

    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    manager = PluginRuntimeManager(
        tmp_path,
        FakeInstaller(_installed(tmp_path)),  # type: ignore[arg-type]
        registry,
        client_factory=factory,  # type: ignore[arg-type]
    )

    assert await manager.start("desktop-pet") is True

    assert registry.has_tool("pet_action")
    assert not registry.has_tool("undeclared_tool")
    assert registry.get_always_on_names() == {"pet_action"}
    assert clients[0].kwargs["inherit_env"] is False
    assert "SHIORI_PLUGIN_DATA_DIR" in clients[0].kwargs["env"]
    assert "GITHUB_TOKEN" not in clients[0].kwargs["env"]
    assert await registry.execute("pet_action", {"target": "center"}) == "ok"
    assert clients[0].calls == [("pet_action", {"target": "center"})]

    assert await manager.stop("desktop-pet") is True
    assert not registry.has_tool("pet_action")
    assert clients[0].disconnected is True


@pytest.mark.asyncio
async def test_runtime_unregisters_tools_when_plugin_process_exits(
    tmp_path: Path,
) -> None:
    registry = ToolRegistry()
    clients: list[FakeClient] = []

    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    manager = PluginRuntimeManager(
        tmp_path,
        FakeInstaller(_installed(tmp_path)),  # type: ignore[arg-type]
        registry,
        client_factory=factory,  # type: ignore[arg-type]
    )
    await manager.start("desktop-pet")

    clients[0].exited.set()
    for _ in range(10):
        if not registry.has_tool("pet_action"):
            break
        await asyncio.sleep(0)

    assert manager.running_plugin_ids == ()
    assert not registry.has_tool("pet_action")


@pytest.mark.asyncio
async def test_runtime_refuses_disabled_plugin(tmp_path: Path) -> None:
    manager = PluginRuntimeManager(
        tmp_path,
        FakeInstaller(_installed(tmp_path, enabled=False)),  # type: ignore[arg-type]
        ToolRegistry(),
        client_factory=FakeClient,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="disabled"):
        await manager.start("desktop-pet")


@pytest.mark.asyncio
async def test_runtime_allows_only_manifest_declared_desktop_rpc(
    tmp_path: Path,
) -> None:
    registry = ToolRegistry()
    clients: list[FakeClient] = []

    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    manager = PluginRuntimeManager(
        tmp_path,
        FakeInstaller(_installed(tmp_path)),  # type: ignore[arg-type]
        registry,
        client_factory=factory,  # type: ignore[arg-type]
    )
    await manager.start("desktop-pet")

    assert await manager.call_rpc("desktop-pet", "pet.state", {"role_id": "r1"}) == "ok"
    assert clients[0].calls[-1] == ("pet_state", {"role_id": "r1"})
    with pytest.raises(PermissionError, match="not declared"):
        await manager.call_rpc("desktop-pet", "secret.dump", {})
