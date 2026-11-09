"""Exercise provider publication, actual import and presentation through its public seam."""

from pathlib import Path
import pytest

from shiori_sdk.core.services import DEPENDENCIES, SERVICES
from shiori_sdk.testing.extensions import FakeDependencies
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.services import FakePluginServices
from plugins.desktop_pet.backend.providers import PetProviders
from plugins.desktop_pet.backend.rpc import DesktopPetRpcHandlers
from plugins.pet_2d.backend.plugin import setup

REFERENCE = {"plugin_id": "pet_2d", "service_id": "models"}


@pytest.mark.asyncio
async def test_import_prepare_and_disposal_via_declared_dependency(
    tmp_path, avatar_package
):
    ctx = FakeServiceContext(
        "pet_2d", tmp_path, package_dir=Path(__file__).resolve().parents[1]
    )
    ctx.fake_roles.create_role(role_id="one", name="One", system_prompt="test")
    desktop = PetProviders(ctx.fake_roles)
    ctx.serve(DEPENDENCIES, FakeDependencies({"desktop_pet": desktop}))
    services = FakePluginServices(ctx)
    ctx.serve(SERVICES, services)
    await setup(ctx)
    rpc = DesktopPetRpcHandlers(role_store=ctx.fake_roles, providers=desktop)
    result = await rpc.pets_import(
        {"role_id": "one", "provider": REFERENCE, "source": str(avatar_package.write())}
    )
    model = result["package"]
    assert model["actions"] == [] and model["display_name"] == "Synthetic Avatar"
    assert result["selected_model"] is None
    command = {
        "request_id": "r",
        "lease_id": "l",
        "role_id": "one",
        "model_id": model["id"],
        "op": "prepare",
        "model_data": {"untrusted": True},
    }
    with pytest.raises(ValueError, match="尚未就绪"):
        await services.methods["models", "present"](command)
    await ctx.fake_rpc.handlers["presentation.ready"]({"ready": True})
    assert await services.methods["models", "present"](command) == {"accepted": True}
    method, event = ctx.fake_rpc.events[-1]
    assert method == "presentation.command"
    model_data = event["model_data"]
    assert isinstance(model_data, dict)
    assert model_data["schema"] == "prelulu-avatar-package/v1"
    assert "untrusted" not in model_data
    assert model_data["baked"]["hair"]["layers"][0]["nx"] == 1
    for image in model_data["images"]:
        assert (
            Path(image["image_path"]).read_bytes()
            == avatar_package.files[image["file"]]
        )
    await ctx.aclose()
    assert not desktop.list() and not services.methods and not ctx.fake_rpc.handlers


@pytest.mark.asyncio
async def test_missing_dependency_does_not_publish_a_partial_provider(tmp_path):
    ctx = FakeServiceContext(
        "pet_2d", tmp_path, package_dir=Path(__file__).resolve().parents[1]
    )
    with pytest.raises(KeyError, match="desktop_pet"):
        await setup(ctx)
    assert not ctx.fake_rpc.handlers
