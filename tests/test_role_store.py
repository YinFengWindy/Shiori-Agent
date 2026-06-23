from __future__ import annotations

from pathlib import Path

from core.roles import RoleStore


def test_role_store_creates_manifest_and_assets_layout(tmp_path: Path):
    store = RoleStore(tmp_path)

    assert (tmp_path / "roles" / "roles.json").exists()
    assert (tmp_path / "roles" / "assets").is_dir()
    assert store.list_roles() == []


def test_role_store_creates_role_and_copies_assets(tmp_path: Path):
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"avatar")
    illustration = tmp_path / "ill-1.png"
    illustration.write_bytes(b"ill")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        avatar_source=avatar,
        illustration_sources=[illustration],
    )

    assert role.id.startswith("role-")
    assert role.avatar is not None
    assert role.illustrations
    avatar_path = tmp_path / "roles" / role.avatar
    ill_path = tmp_path / "roles" / role.illustrations[0]
    assert avatar_path.read_bytes() == b"avatar"
    assert ill_path.read_bytes() == b"ill"


def test_role_store_updates_and_deletes_role(tmp_path: Path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
    )

    updated = store.update_role(
        role.id,
        name="Mira Prime",
        system_prompt="you are still mira",
        description="updated",
    )
    assert updated.name == "Mira Prime"
    assert updated.system_prompt == "you are still mira"
    assert updated.description == "updated"
    assert store.get_role("mira") is not None
    assert store.delete_role("mira") is True
    assert store.get_role("mira") is None


def test_role_store_replaces_and_clears_old_assets(tmp_path: Path):
    avatar1 = tmp_path / "avatar-1.png"
    avatar1.write_bytes(b"avatar-1")
    avatar2 = tmp_path / "avatar-2.png"
    avatar2.write_bytes(b"avatar-2")
    ill1 = tmp_path / "ill-1.png"
    ill1.write_bytes(b"ill-1")

    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        description="assistant role",
        system_prompt="you are mira",
        role_id="mira",
        avatar_source=avatar1,
        illustration_sources=[ill1],
    )
    first_avatar = tmp_path / "roles" / role.avatar
    first_illustration = tmp_path / "roles" / role.illustrations[0]
    assert first_avatar.exists()
    assert first_illustration.exists()

    updated = store.update_role(
        "mira",
        avatar_source=avatar2,
        clear_illustrations=True,
    )
    assert updated.avatar is not None
    assert (tmp_path / "roles" / updated.avatar).read_bytes() == b"avatar-2"
    assert not first_avatar.exists()
    assert not first_illustration.exists()

    cleared = store.update_role("mira", clear_avatar=True)
    assert cleared.avatar is None
