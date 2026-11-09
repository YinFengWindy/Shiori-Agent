"""Durable installation, interruption recovery and cross-role asset isolation."""

from copy import deepcopy
import pytest
from shiori_sdk.testing.roles import FakeRoles

from plugins.pet_2d.backend.packages import AvatarPackages
from plugins.pet_2d.backend.storage import model_directory, reconcile


def service(tmp_path):
    roles = FakeRoles(tmp_path)
    for role_id in ("one", "two"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    roles.extensions.values["desktop_pet"] = {
        "one": {"desktop_pet_enabled": False, "selected_model": None}
    }
    return roles, AvatarPackages(roles, tmp_path)


def test_import_preserves_original_documents_and_role_intent(tmp_path, avatar_package):
    roles, packages = service(tmp_path)
    source = avatar_package.write()
    original = source.read_bytes()
    intent = deepcopy(roles.extensions.values["desktop_pet"])
    record = packages.import_package("one", str(source))
    loaded = packages.load("one", record["id"])
    assert loaded.display_name == "Synthetic Avatar"
    assert loaded.body == {"width": 280, "height": 280}
    assert loaded.baked["mouth"]["parametric"]["fit"]["style"]["halfWidth"] == 1
    assert source.read_bytes() == original
    assert roles.extensions.values["desktop_pet"] == intent
    assert packages.import_package("one", str(source)) == record
    assert len(packages.store.list_models("one")) == 1
    with pytest.raises(KeyError, match="不存在"):
        packages.load("two", record["id"])


@pytest.mark.parametrize("after_commit", [False, True])
def test_metadata_failure_retains_existing_models_and_retry_recovers(
    tmp_path, avatar_package, monkeypatch, after_commit
):
    roles, packages = service(tmp_path)
    source = avatar_package.write()
    first = packages.import_package("one", str(source))
    avatar_package.manifest["version"] = "test-v2"
    source = avatar_package.write()
    update = roles.extensions.update

    def fail(namespace, mutate):
        if after_commit:
            update(namespace, mutate)
        raise OSError("metadata write failed")

    with monkeypatch.context() as patch:
        patch.setattr(roles.extensions, "update", fail)
        with pytest.raises(OSError, match="metadata write failed"):
            packages.import_package("one", str(source))
    assert packages.load("one", first["id"]).model_id == first["id"]
    second = packages.import_package("one", str(source))
    assert second["id"] != first["id"]
    assert len(packages.store.list_models("one")) == 2
    assert packages.load("one", second["id"]).model_id == second["id"]


def test_directory_failure_does_not_publish_a_half_model(
    tmp_path, avatar_package, monkeypatch
):
    roles, packages = service(tmp_path)
    source = avatar_package.write()
    import plugins.pet_2d.backend.packages as module

    with monkeypatch.context() as patch:
        patch.setattr(
            module.os,
            "rename",
            lambda *_: (_ for _ in ()).throw(OSError("directory locked")),
        )
        with pytest.raises(OSError, match="directory locked"):
            packages.import_package("one", str(source))
    assert packages.store.list_models("one") == []
    assert not list((tmp_path / "plugin-data/pet_2d/models-one").iterdir())
    assert packages.import_package("one", str(source))["id"]


def test_conflicting_version_cannot_overwrite_installed_content(
    tmp_path, avatar_package
):
    _, packages = service(tmp_path)
    first = packages.import_package("one", str(avatar_package.write()))
    avatar_package.manifest["name"] = "Changed content same version"
    with pytest.raises(ValueError, match="不能覆盖"):
        packages.import_package("one", str(avatar_package.write()))
    assert packages.load("one", first["id"]).display_name == "Synthetic Avatar"


def test_delete_persistence_failure_and_orphan_cleanup_preserve_other_roles(
    tmp_path, avatar_package, monkeypatch
):
    roles, packages = service(tmp_path)
    source = str(avatar_package.write())
    one = packages.import_package("one", source)
    two = packages.import_package("two", source)
    with monkeypatch.context() as patch:
        patch.setattr(
            roles.extensions,
            "update",
            lambda *_: (_ for _ in ()).throw(OSError("metadata locked")),
        )
        with pytest.raises(OSError):
            packages.remove("one", one["id"])
    assert packages.load("one", one["id"]).model_id == one["id"]
    del roles.values["one"]
    reconcile(roles, tmp_path)
    assert not (tmp_path / "plugin-data/pet_2d/models-one").exists()
    assert packages.load("two", two["id"]).model_id == two["id"]


def test_installed_tampering_is_refused_before_asset_grant(tmp_path, avatar_package):
    _, packages = service(tmp_path)
    record = packages.import_package("one", str(avatar_package.write()))
    source = model_directory(tmp_path, "one", record["id"]) / "rig/baked.json"
    source.write_bytes(b"{}")
    with pytest.raises(ValueError, match="完整性"):
        packages.load("one", record["id"])
    assert packages.store.list_models("one")[0]["id"] == record["id"]


def test_unsupported_mouth_is_rejected_before_publish_without_changing_selection(
    tmp_path, avatar_package
):
    roles, packages = service(tmp_path)
    original = packages.import_package("one", str(avatar_package.write()))
    roles.extensions.values["desktop_pet"]["one"] = {
        "desktop_pet_enabled": True,
        "selected_model": {
            "provider": {"plugin_id": "pet_2d", "service_id": "models"},
            "model_id": original["id"],
        },
    }
    before = deepcopy(roles.extensions.values)
    avatar_package.manifest["version"] = "test-v2"
    avatar_package.edit(
        "rig/baked.json", lambda data: data["mouth"].update(parametric=None)
    )
    with pytest.raises(ValueError, match="mouth.parametric"):
        packages.import_package("one", str(avatar_package.write()))
    assert roles.extensions.values == before
    assert packages.load("one", original["id"]).model_id == original["id"]
    assert [
        entry.name for entry in (tmp_path / "plugin-data/pet_2d/models-one").iterdir()
    ] == [original["id"]]
