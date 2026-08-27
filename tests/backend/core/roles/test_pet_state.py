from __future__ import annotations

from core.roles.models import (
    RolePetPackage,
    RoleProactiveConfig,
    RoleRecord,
    default_asset_category,
)
from core.roles.pet_state import RolePetStateStore


def _role(role_id: str, *, enabled: bool = False) -> RoleRecord:
    package = RolePetPackage(
        id="pet",
        format="codex-v2",
        display_name="Pet",
        manifest_path=f"assets/{role_id}/pets/pet/pet.json",
        spritesheet_path=f"assets/{role_id}/pets/pet/spritesheet.webp",
        imported_at="2026-01-01T00:00:00+00:00",
    )
    return RoleRecord(
        id=role_id,
        name=role_id,
        description="",
        system_prompt="fixture",
        background="",
        avatar=None,
        chat_background=None,
        illustrations=[],
        asset_categories=[default_asset_category()],
        asset_category_bindings={},
        runtime_config={},
        channel_bindings=[],
        proactive=RoleProactiveConfig(),
        memory_init_state={},
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        pet_packages=[package],
        selected_pet_package_id="pet",
        desktop_pet_enabled=enabled,
    )


def test_pet_state_enables_only_one_role() -> None:
    first = _role("first", enabled=True)
    second = _role("second")

    RolePetStateStore.set_enabled([first, second], second, True)

    assert first.desktop_pet_enabled is False
    assert second.desktop_pet_enabled is True
