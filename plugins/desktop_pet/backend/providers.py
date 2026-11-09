"""Provider registration and model lookup for desktop consumers."""

from collections.abc import Callable
from typing import Any
from shiori_sdk.roles import Roles
from shiori_sdk.services import ServiceReference
from .api import PetModelProvider
from .models import RolePetState, SelectedModel
from .pet_state import RolePetStateStore
from .storage import PLUGIN_ID


class PetProviders:
    """Generation-owned registry; unloading never erases persisted choices."""

    def __init__(self, roles: Roles) -> None:
        self.roles = roles
        self.state = RolePetStateStore(roles)
        self._providers: dict[tuple[str, str], PetModelProvider] = {}

    def register(self, provider: PetModelProvider) -> Callable[[], None]:
        """Register a provider until its effect is disposed."""
        key = self._key(provider.reference)
        if key in self._providers:
            raise ValueError(f"形象提供者重复: {key}")
        self._providers[key] = provider

        def remove() -> None:
            if self._providers.get(key) is provider:
                del self._providers[key]

        return remove

    def require(self, reference: ServiceReference) -> PetModelProvider:
        """Fail for missing providers while preserving their selections."""
        provider = self._providers.get(self._key(reference))
        if provider is None:
            raise ValueError(
                f"形象提供者不可用: {reference['plugin_id']}/{reference['service_id']}"
            )
        return provider

    def list(self) -> list[PetModelProvider]:
        """Providers active in this runtime generation."""
        return list(self._providers.values())

    def model(self, role_id: str, selection: SelectedModel) -> dict[str, Any]:
        """Resolve a model through its owner."""
        return self.require(selection["provider"]).get_model(
            role_id, selection["model_id"]
        )

    def legacy_state(self, role_id: str) -> dict[str, Any] | None:
        """Expose old format upgrade metadata to its dependent provider."""
        self.state.require_role(role_id)
        value = self.roles.extensions.read(PLUGIN_ID).get(role_id, {})
        return (
            dict(value) if isinstance(value, dict) and "pet_packages" in value else None
        )

    def adopt_legacy(
        self, role_id: str, model_id: str | None, provider: ServiceReference
    ) -> None:
        """Retire old metadata after the provider commits recoverable copies."""
        with self.roles.read_scope():
            self.state.require_role(role_id)

            def adopt(data):
                old = data.get(role_id, {})
                if "pet_packages" not in old:
                    return
                state = RolePetState.from_dict(role_id, old)
                if "selected_model" not in old:
                    state.selected_model = (
                        {"provider": provider, "model_id": model_id}
                        if model_id
                        else None
                    )
                data[role_id] = state.to_dict()

            self.roles.extensions.update(PLUGIN_ID, adopt)

    @staticmethod
    def _key(reference: ServiceReference) -> tuple[str, str]:
        return reference["plugin_id"], reference["service_id"]
