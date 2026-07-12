from __future__ import annotations

from core.roles import RoleStore
from desktop_bridge.role_presenter import DesktopRolePresenter


def test_role_presenter_serializes_desktop_asset_fields(tmp_path) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )

    payload = DesktopRolePresenter(store).serialize(role)

    assert payload["id"] == role.id
    assert payload["avatar_abs"] is None
    assert payload["illustrations_abs"] == []
    assert payload["asset_categories"] == [
        {"id": "default", "name": "默认", "allow_role_send": False}
    ]
    assert payload["asset_category_bindings"] == {}
