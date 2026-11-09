"""Provider readiness and accepted commands never imply presentation completion."""

from pathlib import Path
import pytest
from shiori_sdk.testing.memory_context import FakeRpc
from shiori_sdk.testing.roles import FakeRoles
from plugins.pet_codex_sprite.backend.models import RolePetPackage
from plugins.pet_codex_sprite.backend.pet_state import RolePetStateStore
from plugins.pet_codex_sprite.backend.provider import SpriteModels
from plugins.pet_codex_sprite.backend.presentation import SpritePresentation


@pytest.mark.asyncio
async def test_preparation_requires_ready_and_overrides_untrusted_asset_fields(
    tmp_path,
):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="role", name="Role", system_prompt="test")
    root = tmp_path / "plugin-data/pet_codex_sprite/pets-role/pet"
    root.mkdir(parents=True)
    (root / "spritesheet.webp").write_bytes(b"sprite")
    RolePetStateStore(roles).replace_packages(
        "role",
        [
            RolePetPackage(
                "pet",
                "codex-sprite@1",
                "Pet",
                "plugin-data/pet_codex_sprite/pets-role/pet/pet.json",
                "plugin-data/pet_codex_sprite/pets-role/pet/spritesheet.webp",
                "then",
                actions={"greet": "waving"},
            )
        ],
    )
    rpc = FakeRpc()
    presentation = SpritePresentation(SpriteModels(roles, tmp_path), rpc)
    command = {
        "request_id": "request",
        "lease_id": "lease",
        "role_id": "role",
        "model_id": "pet",
        "op": "prepare",
        "spritesheet_abs": "untrusted",
        "actions": {"bad": "bad"},
    }
    with pytest.raises(ValueError, match="尚未就绪"):
        await presentation.present(command)
    assert not rpc.events
    await presentation.set_ready({"ready": True})
    assert await presentation.present(command) == {"accepted": True}
    event, payload = rpc.events[-1]
    assert event == "presentation.command"
    assert Path(payload["spritesheet_abs"]).read_bytes() == b"sprite"
    assert payload["actions"] == {"greet": "waving"}
    assert payload["lease_id"] == "lease"
    with pytest.raises(KeyError):
        await presentation.present({**command, "model_id": "missing"})
    assert len(rpc.events) == 1
    await presentation.present({**command, "op": "hide"})
    await presentation.set_ready({"ready": False})
    with pytest.raises(ValueError, match="尚未就绪"):
        await presentation.present(command)


@pytest.mark.asyncio
async def test_transport_loss_revokes_ready(tmp_path):
    class Disconnected(FakeRpc):
        async def emit(self, name, payload):
            return False

    presentation = SpritePresentation(
        SpriteModels(FakeRoles(tmp_path), tmp_path), Disconnected()
    )
    await presentation.set_ready({"ready": True})
    with pytest.raises(ValueError, match="未接收"):
        await presentation.present(
            {
                "request_id": "r",
                "lease_id": "l",
                "role_id": "role",
                "model_id": "pet",
                "op": "close",
            }
        )
    assert not presentation.ready
