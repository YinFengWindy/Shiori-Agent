"""Short management RPCs; registry owns finite asynchronous operations."""

from functools import partial
from typing import Any
from shiori_sdk.core.services import RPC
from shiori_sdk.rpc import Concurrency, PluginRpcError
from shiori_sdk.runtime import PluginRuntimeContext
from .models import McpConfigError
from .registry import McpServerRegistry


class McpManagement:
    """Project state and validate errors before they cross the bridge."""

    def __init__(self, registry: McpServerRegistry):
        self.registry = registry

    def register(self, ctx: PluginRuntimeContext) -> None:
        """Declare finite names for generated RPC contracts."""
        rpc = ctx.require(RPC)
        rpc.register("servers.list", self.list, concurrency=Concurrency.READ_ONLY)
        for method in ("save", "delete", "set_enabled", "test", "reconnect"):
            rpc.register(f"servers.{method}", partial(self.mutate, method))
        rpc.register(
            "operations.cancel", partial(self.mutate, "cancel"), admission_exempt=True
        )

    async def list(self, _payload: dict[str, object]) -> dict[str, object]:
        """Read public status even while an operation waits for a peer."""
        return self.registry.snapshot()

    async def mutate(self, method: str, payload: dict[str, Any]) -> dict[str, object]:
        """Never expose validation inputs, OS command lines or exception chains."""
        try:
            server = str(payload.get("server_id", ""))
            revision = payload.get("expected_revision")
            if method == "save":
                return self.registry.save(payload)
            if method == "delete":
                return self.registry.delete(server, revision)
            if method == "set_enabled":
                return self.registry.set_enabled(
                    server, payload.get("enabled"), revision
                )
            if method == "cancel":
                return self.registry.cancel_operation(server)
            return self.registry.start_operation(
                server, "test" if method == "test" else "connect"
            )
        except McpConfigError as error:
            raise PluginRpcError("mcp_invalid_operation", str(error)) from None
        except Exception:
            raise PluginRpcError(
                "mcp_storage_failed", "MCP 设置未能保存，原配置已保留"
            ) from None
