"""Pet RPC import delegates only validated private staging sources."""

import asyncio
from pathlib import Path
import pytest
from plugins.desktop_pet.backend.pet_state import RolePetStateStore

from shiori_sdk.testing.roles import FakeRoles
from shiori_sdk.testing.memory import FakeMemoryStorage
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.rpc import DesktopPetRpcHandlers


def test_pet_import_passes_staged_source_to_service_and_refuses_outside_before_import(
    tmp_path, monkeypatch
):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    handlers = DesktopPetRpcHandlers(
        role_store=roles, workspace=tmp_path, storage=FakeMemoryStorage()
    )
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


def _bind_pet(workspace, *, enabled=True, with_file=True, store):
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    state = RolePetStateStore(store)
    root = "plugin-data/desktop_pet/pets-mira/pet-1"
    state.replace_packages(
        "mira",
        [
            RolePetPackage(
                "pet-1",
                "codex-sprite@1",
                "Pet",
                f"{root}/pet.json",
                f"{root}/spritesheet.webp",
                "today",
                actions={"greeting": "waving"},
            )
        ],
    )
    state.select_package("mira", "pet-1")
    state.set_enabled("mira", enabled)
    if with_file:
        target = workspace / root / "spritesheet.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not-a-real-webp")


def _handlers(workspace, roles):
    return DesktopPetRpcHandlers(
        role_store=roles, workspace=workspace, storage=FakeMemoryStorage()
    )


def _resolve(handlers, method):
    return {
        "binding.get": handlers.binding_get,
        "pets.list": handlers.pets_list,
        "pets.import": handlers.pets_import,
        "pets.remove": handlers.pets_remove,
        "pets.select": handlers.pets_select,
    }[method]


def test_binding_get_returns_the_selected_package(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, store=store)
    handlers = _handlers(tmp_path, store)
    resolved = handlers.binding_get
    assert resolved is not None

    result = asyncio.run(resolved({}))

    assert result is not None
    binding = result["binding"]
    assert binding is not None
    assert binding["role_id"] == "mira"
    assert binding["actions"] == {"greeting": "waving"}
    package = binding["package"]
    assert package["id"] == "pet-1"
    assert package["display_name"] == "Pet"
    # Absolute, and named `spritesheet_abs` so the desktop bridge grants it a
    # `shiori-asset://` URL on the way to the renderer.
    assert (
        Path(package["spritesheet_abs"])
        == (
            tmp_path / "plugin-data/desktop_pet/pets-mira/pet-1/spritesheet.webp"
        ).resolve()
    )

    assert Path(package["spritesheet_abs"]).read_bytes() == b"not-a-real-webp"


def test_binding_get_ignores_a_role_whose_pet_is_switched_off(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, enabled=False, store=store)
    handlers = _handlers(tmp_path, store)
    resolved = handlers.binding_get
    assert resolved is not None

    # A role keeps its package after the user switches the pet off; only
    # `desktop_pet_enabled` says whether to render it.
    assert asyncio.run(resolved({})) == {"binding": None}


def test_binding_get_reports_nothing_when_the_spritesheet_is_missing(
    tmp_path: Path,
) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, with_file=False, store=store)
    handlers = _handlers(tmp_path, store)
    resolved = handlers.binding_get
    assert resolved is not None

    assert asyncio.run(resolved({})) == {"binding": None}


def test_binding_get_reports_nothing_when_no_role_has_a_pet(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _ = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    handlers = _handlers(tmp_path, store)
    resolved = handlers.binding_get
    assert resolved is not None

    assert asyncio.run(resolved({})) == {"binding": None}


def test_pets_list_returns_the_rows_roles_list_used_to_carry(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, store=store)
    handlers = _handlers(tmp_path, store)

    result = asyncio.run(_resolve(handlers, "pets.list")({"role_id": "mira"}))

    assert result is not None
    assert result["selected_package_id"] == "pet-1"
    package = result["packages"][0]
    assert package["id"] == "pet-1"
    assert package["display_name"] == "Pet"
    # The two names the desktop grants `shiori-asset://` URLs for; they are the
    # contract, so they must match what `role_presenter` emitted.
    assert Path(package["spritesheet_abs"]).is_absolute()
    assert package["preview_abs"] is None


def test_pets_select_and_remove_go_through_the_shared_store(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, store=store)
    handlers = _handlers(tmp_path, store)

    after_remove = asyncio.run(
        _resolve(handlers, "pets.remove")({"role_id": "mira", "package_id": "pet-1"})
    )

    assert after_remove == {"selected_package_id": None, "packages": []}
    # Written through the host's own store, so the host sees it without a reload.
    role = RolePetStateStore(store).require_role("mira")
    assert role.pet_packages == []
    # Removing the selected package also switches the pet off — that invariant
    # lives in `pet_state.replace_packages` and must survive the move.
    assert role.desktop_pet_enabled is False


def test_pet_rpc_requires_the_ids_it_acts_on(tmp_path: Path) -> None:
    store = FakeRoles(tmp_path)
    _bind_pet(tmp_path, store=store)
    handlers = _handlers(tmp_path, store)

    for method, payload in [
        ("pets.list", {}),
        ("pets.import", {"role_id": "mira"}),
        ("pets.remove", {"role_id": "mira"}),
        ("pets.select", {"role_id": "mira"}),
        ("pets.select", {"package_id": "pet-1"}),
    ]:
        with pytest.raises((ValueError, KeyError)):
            asyncio.run(_resolve(handlers, method)(payload))
