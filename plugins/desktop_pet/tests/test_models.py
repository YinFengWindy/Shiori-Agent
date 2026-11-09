"""Persisted intent survives provider absence and reads old selections."""

import pytest
from plugins.desktop_pet.backend.models import RolePetState

REFERENCE = {
    "provider": {"plugin_id": "test_provider", "service_id": "models"},
    "model_id": "model",
}


def test_reference_survives_without_provider_metadata():
    value = {"selected_model": REFERENCE, "desktop_pet_enabled": True}
    state = RolePetState.from_dict("role", value)
    assert state.to_dict() == value
    assert (
        RolePetState.from_dict(
            "role", {"selected_model": None, "desktop_pet_enabled": True}
        ).desktop_pet_enabled
        is False
    )


def test_legacy_selection_is_projected_without_changing_source():
    value = {
        "pet_packages": [{"id": "pet"}],
        "selected_pet_package_id": "pet",
        "desktop_pet_enabled": True,
    }
    state = RolePetState.from_dict("role", value)
    assert state.selected_model == {
        "provider": {"plugin_id": "pet_codex_sprite", "service_id": "models"},
        "model_id": "pet",
    }
    assert state.desktop_pet_enabled
    assert "selected_model" not in value
    with pytest.raises(ValueError):
        RolePetState.from_dict(
            "role", {"selected_model": {"provider": {}, "model_id": "pet"}}
        )
