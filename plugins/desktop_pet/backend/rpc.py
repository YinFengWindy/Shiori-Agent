"""Format-independent model management and binding RPC projections."""

from typing import Any
from shiori_sdk.roles import Roles
from .models import SelectedModel, read_provider
from .pet_state import RolePetStateStore
from .providers import PetProviders


class DesktopPetRpcHandlers:
    """Manage desktop choices through provider-owned synchronous operations."""

    def __init__(self, *, role_store: Roles, providers: PetProviders) -> None:
        self._state = RolePetStateStore(role_store)
        self._providers = providers

    async def pets_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return public model descriptors and each provider's import policy."""
        role = self._state.require_role(require_role_id(payload))
        providers = self._providers.list()
        return {
            "selected_model": role.selected_model,
            "providers": [
                {**p.reference, "label": p.label, "import": p.import_options}
                for p in providers
            ],
            "packages": [
                {**m, "provider": p.reference}
                for p in providers
                for m in p.list_models(role.id)
            ],
        }

    async def pets_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delegate staging validation and installation to the selected provider."""
        role_id = require_role_id(payload)
        self._state.require_role(role_id)
        provider = self._providers.require(read_provider(payload.get("provider")))
        source = require_text(payload, "source")
        model = provider.import_model(role_id, source)
        return {
            "package": {**model, "provider": provider.reference},
            **await self.pets_list(payload),
        }

    async def pets_remove(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Retire selection before deleting its assets so failure cannot leave a dangling enabled model."""
        role_id = require_role_id(payload)
        reference = read_provider(payload.get("provider"))
        model_id = require_text(payload, "model_id")
        provider = self._providers.require(reference)
        with self._state.roles.read_scope():
            role = self._state.require_role(role_id)
            provider.get_model(role_id, model_id)
            if role.selected_model == {"provider": reference, "model_id": model_id}:
                self._state.select_model(role_id, None)
            provider.remove_model(role_id, model_id)
        return await self.pets_list(payload)

    async def pets_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Commit a successfully prepared selection; never enable an inactive role."""
        role_id = require_role_id(payload)
        reference = read_provider(payload.get("provider"))
        model_id = require_text(payload, "model_id")
        with self._state.roles.read_scope():
            self._state.require_role(role_id)
            self._providers.require(reference).get_model(role_id, model_id)
            self._state.select_model(
                role_id, {"provider": reference, "model_id": model_id}
            )
        return await self.pets_list(payload)

    async def binding_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Resolve a candidate without touching selection, enablement or assets."""
        role_id = require_role_id(payload)
        self._state.require_role(role_id)
        selection: SelectedModel = {
            "provider": read_provider(payload.get("provider")),
            "model_id": require_text(payload, "model_id"),
        }
        return {
            "binding": {
                "role_id": role_id,
                "provider": selection["provider"],
                "model": self._providers.model(role_id, selection),
            }
        }

    async def binding_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Resolve the enabled role; missing providers are explicit failures."""
        role = next(
            (r for r in self._state.list_roles() if r.desktop_pet_enabled), None
        )
        if role is None or role.selected_model is None:
            return {"binding": None}
        return {
            "binding": {
                "role_id": role.id,
                "provider": role.selected_model["provider"],
                "model": self._providers.model(role.id, role.selected_model),
            }
        }


def require_role_id(payload: dict[str, Any]) -> str:
    """Read the shared role-scoped RPC identity."""
    return require_text(payload, "role_id")


def require_text(payload: dict[str, Any], key: str) -> str:
    """Reject missing or non-text identifiers rather than coercing objects."""
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少 {key}")
    return value.strip()
