"""Independent public-service publication double; no host or network is imported."""

from collections.abc import Mapping

from shiori_sdk.services import ServiceHandler, ServiceProviderContext
from .context import FakePluginContext


class FakePluginServices:
    """Store explicit handlers until the owning SDK test context is disposed."""

    def __init__(self, context: FakePluginContext) -> None:
        self._context = context
        self.entries: dict[str, dict[str, object]] = {}
        self.methods: dict[tuple[str, str], ServiceHandler] = {}

    def register(
        self,
        service_id: str,
        *,
        contract: str,
        label: str,
        methods: Mapping[str, ServiceHandler],
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Record one service with a cleanup registered before it becomes visible."""
        if service_id in self.entries:
            raise ValueError("Service already registered")

        def remove() -> None:
            self.entries.pop(service_id, None)
            for name in methods:
                self.methods.pop((service_id, name), None)

        self._context.effect(f"service:{service_id}", remove)
        self.entries[service_id] = {
            "plugin_id": self._context.plugin_id,
            "service_id": service_id,
            "contract": contract,
            "label": label,
            "metadata": dict(metadata or {}),
        }
        for name, handler in methods.items():
            self.methods[service_id, name] = handler


class FakeServiceProviderContext(FakePluginContext):
    """Minimal independent setup context for dynamically discoverable providers."""

    def __init__(self, plugin_id: str):
        super().__init__(plugin_id, capabilities=("services",))
        self.services = FakePluginServices(self)

    def as_capability(self) -> ServiceProviderContext:
        """Check the same typed provider setup surface as the production host."""
        return self
