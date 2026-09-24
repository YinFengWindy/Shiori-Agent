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


def test_role_presenter_attaches_the_chat_list_preview(tmp_path) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )
    preview = {
        "role": "assistant",
        "content": "早呀",
        "timestamp": "t",
        "has_media": False,
    }
    requested: list[str] = []

    def last_message_for_role(role_id: str):
        requested.append(role_id)
        return preview

    payload = DesktopRolePresenter(
        store, last_message_for_role=last_message_for_role
    ).serialize(role)

    assert payload["last_message"] == preview
    assert requested == ["mira"]


def test_role_presenter_omits_the_preview_without_a_reader(tmp_path) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira", name="Mira", description="", system_prompt="You are Mira."
    )

    assert "last_message" not in DesktopRolePresenter(store).serialize(role)
