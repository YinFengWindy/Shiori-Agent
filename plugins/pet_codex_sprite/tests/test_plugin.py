"""The independent package publishes services only with its declared dependency."""

from pathlib import Path
import pytest
from shiori_sdk.core.services import DEPENDENCIES, SERVICES
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.services import FakePluginServices
from shiori_sdk.testing.extensions import FakeDependencies
from plugins.desktop_pet.backend.providers import PetProviders
from plugins.pet_codex_sprite.backend.plugin import setup


@pytest.mark.asyncio
async def test_setup_dependency_and_disposal_leave_no_registered_provider(tmp_path):
    ctx = FakeServiceContext(
        "pet_codex_sprite", tmp_path, package_dir=Path(__file__).resolve().parents[1]
    )
    desktop = PetProviders(ctx.fake_roles)
    ctx.serve(DEPENDENCIES, FakeDependencies({"desktop_pet": desktop}))
    services = FakePluginServices(ctx)
    ctx.serve(SERVICES, services)
    await setup(ctx)
    ctx.fake_roles.create_role(role_id="role", name="Role", system_prompt="test")
    assert await services.methods["models", "list"]({"role_id": "role"}) == {
        "models": []
    }
    assert services.entries["models"]["contract"] == "shiori.pet-models.v1"
    with pytest.raises(ValueError, match="尚未就绪"):
        await services.methods["models", "present"]({"op": "prepare"})
    await ctx.aclose()
    assert desktop.list() == [] and not services.methods
    with pytest.raises(ValueError, match="不可用"):
        desktop.require({"plugin_id": "pet_codex_sprite", "service_id": "models"})


@pytest.mark.asyncio
async def test_missing_dependency_does_not_publish_a_provider(tmp_path):
    ctx = FakeServiceContext(
        "pet_codex_sprite", tmp_path, package_dir=Path(__file__).resolve().parents[1]
    )
    with pytest.raises(KeyError, match="desktop_pet"):
        await setup(ctx)
    assert not ctx.fake_rpc.handlers
