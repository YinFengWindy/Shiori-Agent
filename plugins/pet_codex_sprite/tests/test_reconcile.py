"""Migration retains recoverable source data across each persistence boundary."""

from copy import deepcopy
from pathlib import Path
import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.providers import PetProviders
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.pet_codex_sprite.backend.reconcile import SpriteReconciler
from plugins.pet_codex_sprite.backend.provider import SpriteModels, SPRITE_PROVIDER


@pytest.fixture
def migration(tmp_path):
    roles = FakeRoles(tmp_path)
    for role_id, enabled in (("first", True), ("second", False)):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
        root = tmp_path / "plugin-data" / "desktop_pet" / f"pets-{role_id}" / "pet"
        root.mkdir(parents=True)
        for name in ("pet.json", "spritesheet.webp", "preview.png"):
            (root / name).write_bytes(f"{role_id}:{name}".encode())
        package = {
            "id": "pet",
            "display_name": "Pet",
            "format": "codex-sprite@1",
            "imported_at": "then",
            "actions": {"greet": "waving"},
            **{
                key: (root / name).relative_to(tmp_path).as_posix()
                for key, name in (
                    ("manifest_path", "pet.json"),
                    ("spritesheet_path", "spritesheet.webp"),
                    ("preview_path", "preview.png"),
                )
            },
        }
        roles.extensions.values.setdefault("desktop_pet", {})[role_id] = {
            "pet_packages": [package],
            "selected_pet_package_id": "pet",
            "desktop_pet_enabled": enabled,
        }
    roles.extensions.values["unrelated"] = {"keep": True}
    return roles, SpriteReconciler(roles, tmp_path, PetProviders(roles))


def test_migration_preserves_packages_selection_actions_and_disabled_intent(
    migration, tmp_path
):
    roles, reconcile = migration
    reconcile.reconcile()
    desktop = RolePetStateStore(roles)
    assert desktop.is_enabled("first") and not desktop.is_enabled("second")
    assert desktop.require_role("first").selected_model == {
        "provider": SPRITE_PROVIDER,
        "model_id": "pet",
    }
    models = SpriteModels(roles, tmp_path)
    assert models.get_model("first", "pet")["actions"] == ["greet"]
    assert models.presentation("first", "pet")["actions"] == {"greet": "waving"}
    assert (
        Path(models.presentation("first", "pet")["spritesheet_abs"]).read_bytes()
        == b"first:spritesheet.webp"
    )
    assert roles.extensions.values["unrelated"] == {"keep": True}
    assert not (tmp_path / "plugin-data/desktop_pet/pets-first/pet").exists()
    before = deepcopy(roles.extensions.values)
    reconcile.reconcile()
    assert roles.extensions.values == before


@pytest.mark.parametrize("failing_namespace", ["pet_codex_sprite", "desktop_pet"])
def test_failed_metadata_publish_retains_sources_and_retry_is_lossless(
    migration, tmp_path, monkeypatch, failing_namespace
):
    roles, reconcile = migration
    original = roles.extensions.update

    def fail(namespace, mutate):
        if namespace == failing_namespace:
            raise OSError("metadata locked")
        return original(namespace, mutate)

    with monkeypatch.context() as patch:
        patch.setattr(roles.extensions, "update", fail)
        with pytest.raises(OSError, match="metadata locked"):
            reconcile.reconcile()
    for role_id in ("first", "second"):
        assert (
            tmp_path / f"plugin-data/desktop_pet/pets-{role_id}/pet/spritesheet.webp"
        ).read_bytes() == f"{role_id}:spritesheet.webp".encode()
    reconcile.reconcile()
    assert (
        RolePetStateStore(roles).require_role("first").selected_model["model_id"]
        == "pet"
    )
    assert len(SpriteModels(roles, tmp_path).list_models("first")) == 1


def test_cleanup_failure_retries_after_selection_is_committed(
    migration, tmp_path, monkeypatch
):
    roles, reconcile = migration
    import plugins.pet_codex_sprite.backend.reconcile as module

    with monkeypatch.context() as patch:
        patch.setattr(
            module.shutil,
            "rmtree",
            lambda path: (_ for _ in ()).throw(OSError("file locked")),
        )
        with pytest.raises(OSError, match="file locked"):
            reconcile.reconcile()
    assert any(
        "legacy_cleanup" in value
        for value in roles.extensions.values["pet_codex_sprite"].values()
    )
    reconcile.reconcile()
    assert all(
        "legacy_cleanup" not in value
        for value in roles.extensions.values["pet_codex_sprite"].values()
    )
    assert RolePetStateStore(roles).is_enabled("first")


def test_destination_conflict_does_not_overwrite_user_data(migration, tmp_path):
    roles, reconcile = migration
    target = tmp_path / "plugin-data/pet_codex_sprite/pets-first/pet/spritesheet.webp"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"different package")
    with pytest.raises(ValueError, match="内容冲突"):
        reconcile.reconcile()
    assert target.read_bytes() == b"different package"
    assert (
        tmp_path / "plugin-data/desktop_pet/pets-first/pet/spritesheet.webp"
    ).is_file()
    assert "pet_packages" in roles.extensions.values["desktop_pet"]["first"]
