"""Reconciliation never erases temporarily unavailable model choices."""

from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.reconcile import PetStateReconciler


def test_reconcile_prunes_deleted_roles_and_keeps_one_intent_without_provider(tmp_path):
    roles = FakeRoles(tmp_path)
    reference = {
        "provider": {"plugin_id": "missing", "service_id": "models"},
        "model_id": "pet",
    }
    for role_id in ("first", "second"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    roles.extensions.values["desktop_pet"] = {
        role_id: {"selected_model": reference, "desktop_pet_enabled": True}
        for role_id in ("first", "second", "deleted")
    }
    reconciler = PetStateReconciler(roles, tmp_path)
    reconciler.reconcile()
    values = roles.extensions.read("desktop_pet")
    assert set(values) == {"first", "second"}
    assert values["first"] == {"selected_model": reference, "desktop_pet_enabled": True}
    assert values["second"] == {
        "selected_model": reference,
        "desktop_pet_enabled": False,
    }
    reconciler.reconcile()
    assert roles.extensions.read("desktop_pet") == values
