"""Versioned presentation contract and dependency API for model providers."""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable
from shiori_sdk.services import ServiceReference

PET_MODELS_CONTRACT = "shiori.pet-models.v1"


class PetModelProvider(Protocol):
    """Synchronous operations used by role transactions and tool schemas."""

    reference: ServiceReference
    label: str
    import_options: dict[str, Any]

    def list_models(self, role_id: str) -> list[dict[str, Any]]: ...
    def get_model(self, role_id: str, model_id: str) -> dict[str, Any]: ...
    def import_model(self, role_id: str, source: str) -> dict[str, Any]: ...
    def remove_model(self, role_id: str, model_id: str) -> None: ...


@runtime_checkable
class PetProvidersAPI(Protocol):
    """Published to providers declaring desktop_pet as a dependency."""

    def register(self, provider: PetModelProvider) -> Callable[[], None]: ...
    def legacy_state(self, role_id: str) -> dict[str, Any] | None: ...
    def adopt_legacy(
        self, role_id: str, model_id: str | None, provider: ServiceReference
    ) -> None: ...
