from __future__ import annotations

from core.roles import RoleRelationshipRuntimeService, RoleStore
from desktop_bridge.role_presenter import DesktopRolePresenter
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager


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


def test_role_presenter_exposes_affection_summary_once_initialized(tmp_path) -> None:
    store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    role = store.create_role(
        role_id="mira", name="Mira", description="", system_prompt="You are Mira."
    )
    relationship = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=store,
        session_manager=session_manager,
        presence=PresenceStore(session_manager._store),
    )
    presenter = DesktopRolePresenter(store, relationship)

    assert "affection" not in presenter.serialize(role)
    assert "affection" not in relationship.enrich_session_metadata({"role_id": "mira"})

    relationship.affection.initialize("mira", value=80, reason="挚友")

    summary = {"value": 80, "stage": "挚爱", "progress": 0.0}
    assert presenter.serialize(role)["affection"] == summary
    assert (
        relationship.enrich_session_metadata({"role_id": "mira"})["affection"]
        == summary
    )
