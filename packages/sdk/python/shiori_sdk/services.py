"""Discoverable plugin contracts with explicitly published JSON methods."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, TypedDict

from .runtime import PluginRuntimeContext

type ServiceHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


class ServiceReference(TypedDict):
    """Exact plugin and service identity selected by a consuming plugin."""

    plugin_id: str
    service_id: str


class PluginServices(Protocol):
    """Publish a contract without granting access to other private plugin RPCs."""

    def register(
        self,
        service_id: str,
        *,
        contract: str,
        label: str,
        methods: Mapping[str, ServiceHandler],
        metadata: Mapping[str, object] | None = None,
    ) -> None: ...


class ServiceProviderContext(PluginRuntimeContext, Protocol):
    """Setup context requiring the explicit services manifest capability."""

    @property
    def services(self) -> PluginServices: ...
