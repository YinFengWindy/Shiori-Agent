from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent.mcp.client import McpClient
from agent.plugin_packages import InstalledPlugin, PluginPackageInstaller
from agent.plugin_runtime.tool import PluginMcpTool
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

McpClientFactory = Callable[..., McpClient]


@dataclass
class _RunningPlugin:
    installed: InstalledPlugin
    client: McpClient
    tool_names: tuple[str, ...]
    watcher: asyncio.Task[None] | None = None


class PluginRuntimeManager:
    """Runs installed plugin backends as isolated MCP subprocesses."""

    def __init__(
        self,
        workspace: Path,
        installer: PluginPackageInstaller,
        tool_registry: ToolRegistry,
        *,
        client_factory: McpClientFactory = McpClient,
    ) -> None:
        self._workspace = workspace
        self._installer = installer
        self._tool_registry = tool_registry
        self._client_factory = client_factory
        self._running: dict[str, _RunningPlugin] = {}
        self._lock = asyncio.Lock()

    @property
    def running_plugin_ids(self) -> tuple[str, ...]:
        """Returns stable IDs for plugin backends that are currently connected."""

        return tuple(sorted(self._running))

    async def start_all(self) -> None:
        """Starts every enabled installed backend without blocking other plugins."""

        for installed in self._installer.list_installed():
            if not installed.enabled or installed.manifest.entrypoints.backend is None:
                continue
            try:
                await self.start(installed.plugin_id)
            except Exception as exc:
                logger.error(
                    "plugin backend failed to start (%s): %s",
                    installed.plugin_id,
                    exc,
                )

    async def start(self, plugin_id: str) -> bool:
        """Starts one enabled installed plugin backend and registers its tools."""

        async with self._lock:
            if plugin_id in self._running:
                return False
            installed = self._installed(plugin_id)
            if not installed.enabled:
                raise ValueError(f"plugin is disabled: {plugin_id}")
            backend = installed.manifest.entrypoints.backend
            if backend is None:
                return False
            backend_path = (installed.package_dir / backend).resolve()
            try:
                backend_path.relative_to(installed.package_dir.resolve())
            except ValueError as exc:
                raise ValueError(
                    "plugin backend entrypoint escapes package root"
                ) from exc
            if not backend_path.is_file():
                raise FileNotFoundError(
                    f"plugin backend entrypoint is missing: {backend}"
                )
            command = _backend_command(backend_path)
            data_dir = self._workspace / "private_runtime" / "plugins" / plugin_id
            data_dir.mkdir(parents=True, exist_ok=True)
            client = self._client_factory(
                name=f"plugin_{plugin_id}",
                command=command,
                env=_plugin_environment(plugin_id, data_dir),
                cwd=str(installed.package_dir),
                inherit_env=False,
            )
            registered: list[str] = []
            try:
                infos = await client.connect()
                info_by_name = {info.name: info for info in infos}
                for declaration in installed.manifest.tools:
                    info = info_by_name.get(declaration.remote_name)
                    if info is None:
                        raise ValueError(
                            "plugin backend did not expose declared tool: "
                            f"{declaration.remote_name}"
                        )
                    if self._tool_registry.has_tool(declaration.name):
                        raise ValueError(
                            f"plugin tool name is already registered: {declaration.name}"
                        )
                for declaration in installed.manifest.rpc_methods:
                    if declaration.remote_name not in info_by_name:
                        raise ValueError(
                            "plugin backend did not expose declared RPC method: "
                            f"{declaration.remote_name}"
                        )
                for declaration in installed.manifest.tools:
                    info = info_by_name[declaration.remote_name]
                    tool = PluginMcpTool(
                        client,
                        info,
                        declaration,
                        plugin_name=installed.manifest.name,
                    )
                    self._tool_registry.register(
                        tool,
                        risk=declaration.risk,
                        always_on=declaration.always_on,
                        search_hint=declaration.search_hint,
                        source_type="plugin",
                        source_name=plugin_id,
                    )
                    registered.append(tool.name)
            except Exception:
                for tool_name in registered:
                    self._tool_registry.unregister(tool_name)
                await client.disconnect()
                raise
            running = _RunningPlugin(
                installed=installed,
                client=client,
                tool_names=tuple(registered),
            )
            self._running[plugin_id] = running
            running.watcher = asyncio.create_task(
                self._watch(plugin_id, client),
                name=f"plugin_runtime_watch:{plugin_id}",
            )
            return True

    async def stop(self, plugin_id: str) -> bool:
        """Stops one plugin backend and deterministically unregisters its tools."""

        async with self._lock:
            running = self._running.pop(plugin_id, None)
            if running is None:
                return False
            watcher = running.watcher
            if watcher is not None:
                watcher.cancel()
            for tool_name in running.tool_names:
                self._tool_registry.unregister(tool_name)
            await running.client.disconnect()
        if watcher is not None:
            await asyncio.gather(watcher, return_exceptions=True)
        return True

    async def stop_all(self) -> None:
        """Stops every running plugin backend."""

        for plugin_id in tuple(self._running):
            await self.stop(plugin_id)

    async def call_rpc(
        self,
        plugin_id: str,
        method: str,
        payload: dict[str, object],
    ) -> str:
        """Calls one manifest-allowlisted backend method for a plugin desktop page."""

        running = self._running.get(plugin_id)
        if running is None:
            raise RuntimeError(f"plugin backend is not running: {plugin_id}")
        declaration = next(
            (
                item
                for item in running.installed.manifest.rpc_methods
                if item.method == method
            ),
            None,
        )
        if declaration is None:
            raise PermissionError(f"plugin RPC method is not declared: {method}")
        return await running.client.call(declaration.remote_name, payload)

    async def _watch(self, plugin_id: str, client: McpClient) -> None:
        try:
            exit_code = await client.wait_until_exit()
        except asyncio.CancelledError:
            return
        async with self._lock:
            running = self._running.get(plugin_id)
            if running is None or running.client is not client:
                return
            self._running.pop(plugin_id, None)
            for tool_name in running.tool_names:
                self._tool_registry.unregister(tool_name)
        logger.warning("plugin backend exited (%s): code=%s", plugin_id, exit_code)

    def _installed(self, plugin_id: str) -> InstalledPlugin:
        installed = next(
            (
                item
                for item in self._installer.list_installed()
                if item.plugin_id == plugin_id
            ),
            None,
        )
        if installed is None:
            raise KeyError(f"plugin is not installed: {plugin_id}")
        return installed


def _backend_command(entrypoint: Path) -> list[str]:
    suffix = entrypoint.suffix.lower()
    if suffix in {".py", ".pyz"}:
        return [sys.executable, "-I", str(entrypoint)]
    if suffix == ".exe" and os.name == "nt":
        return [str(entrypoint)]
    raise ValueError(f"unsupported plugin backend entrypoint: {entrypoint.name}")


def _plugin_environment(plugin_id: str, data_dir: Path) -> dict[str, str]:
    allowed_system_names = (
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    )
    environment = {
        name: os.environ[name] for name in allowed_system_names if name in os.environ
    }
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "SHIORI_PLUGIN_ID": plugin_id,
            "SHIORI_PLUGIN_DATA_DIR": str(data_dir),
        }
    )
    return environment
