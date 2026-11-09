"""Model selection validates ownership while preserving failure state."""

from copy import deepcopy
import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.providers import PetProviders
from plugins.desktop_pet.backend.rpc import DesktopPetRpcHandlers


class Provider:
    reference = {"plugin_id": "test_provider", "service_id": "models"}
    label = "Test"
    import_options = {
        "namespace": "test-models",
        "max_file_bytes": 10,
        "extensions": ["zip"],
        "label": "ZIP",
    }

    def __init__(self):
        self.models = {
            "first": {
                "id": "first",
                "display_name": "First",
                "body": {"width": 10, "height": 20},
                "actions": ["wave"],
            }
        }

    def list_models(self, role_id):
        return list(self.models.values())

    def get_model(self, role_id, model_id):
        return self.models[model_id]

    def import_model(self, role_id, source):
        raise ValueError("invalid source")

    def remove_model(self, role_id, model_id):
        del self.models[model_id]


@pytest.fixture
def model_rpc(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="role", name="Role", system_prompt="test")
    providers = PetProviders(roles)
    provider = Provider()
    unregister = providers.register(provider)
    handlers = DesktopPetRpcHandlers(role_store=roles, providers=providers)
    return roles, provider, unregister, handlers


@pytest.mark.asyncio
async def test_preview_does_not_commit_and_select_does_not_enable(model_rpc):
    roles, provider, _, rpc = model_rpc
    payload = {"role_id": "role", "provider": provider.reference, "model_id": "first"}
    before = deepcopy(roles.extensions.values)
    candidate = await rpc.binding_preview(payload)
    assert candidate["binding"]["model"]["actions"] == ["wave"]
    assert roles.extensions.values == before
    result = await rpc.pets_select(payload)
    assert result["selected_model"] == {
        "provider": provider.reference,
        "model_id": "first",
    }
    assert await rpc.binding_get({}) == {"binding": None}
    RolePetStateStore(roles).set_enabled("role", True)
    assert await rpc.binding_get({}) == candidate
    with pytest.raises(KeyError):
        await rpc.pets_select({**payload, "model_id": "missing"})
    assert await rpc.binding_get({}) == candidate


@pytest.mark.asyncio
async def test_provider_disappearance_preserves_selection_and_enablement(model_rpc):
    roles, provider, unregister, rpc = model_rpc
    payload = {"role_id": "role", "provider": provider.reference, "model_id": "first"}
    await rpc.pets_select(payload)
    RolePetStateStore(roles).set_enabled("role", True)
    before = deepcopy(roles.extensions.values)
    unregister()
    with pytest.raises(ValueError, match="提供者不可用"):
        await rpc.binding_get({})
    result = await rpc.pets_list(payload)
    assert result["packages"] == [] and result["providers"] == []
    assert result["selected_model"]["model_id"] == "first"
    assert roles.extensions.values == before


@pytest.mark.asyncio
async def test_remove_selected_model_disables_only_its_role(model_rpc):
    roles, provider, _, rpc = model_rpc
    payload = {"role_id": "role", "provider": provider.reference, "model_id": "first"}
    await rpc.pets_select(payload)
    RolePetStateStore(roles).set_enabled("role", True)
    result = await rpc.pets_remove(payload)
    assert result["selected_model"] is None and result["packages"] == []
    assert not RolePetStateStore(roles).is_enabled("role")
