"""Pet RPC import delegates only validated private staging sources."""

import asyncio

from core.roles.store import RoleStore
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.rpc import DesktopPetRpcHandlers


def test_pet_import_passes_staged_source_to_service_and_refuses_outside_before_import(
    tmp_path, monkeypatch
):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    handlers = DesktopPetRpcHandlers(role_store=roles)
    staging = (
        tmp_path / "private_runtime" / "imports" / "desktop_pet-pets" / "selection"
    )
    staging.mkdir(parents=True)
    selected = staging / "package.zip"
    selected.write_bytes(b"PK")
    calls = []

    def import_package(role_id, source):
        calls.append((role_id, source))
        return RolePetPackage(
            "pet",
            "codex-sprite@1",
            "Pet",
            "plugin-data/desktop_pet/pets-mira/pet/pet.json",
            "plugin-data/desktop_pet/pets-mira/pet/spritesheet.webp",
            "today",
        )

    monkeypatch.setattr(handlers._packages, "import_package", import_package)
    result = asyncio.run(
        handlers.pets_import({"role_id": "mira", "source": str(selected)})
    )
    assert result["package"]["id"] == "pet"
    assert calls == [("mira", selected.resolve())]
    calls.clear()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"PK")
    failure = None
    try:
        asyncio.run(handlers.pets_import({"role_id": "mira", "source": str(outside)}))
    except ValueError as error:
        failure = error
    assert calls == [], "an arbitrary renderer path reached the package importer"
    assert failure is not None and "原生文件选择" in str(failure)
