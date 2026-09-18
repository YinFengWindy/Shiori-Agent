from core.roles.migration import migrate_manifest_payload
import pytest


def test_manifest_v2_migration_is_idempotent_and_preserves_legacy_fields() -> None:
    payload, changed = migrate_manifest_payload(
        {
            "version": 2,
            "roles": [
                {
                    "id": "mira",
                    "system_prompt": "规则",
                    "background": "背景",
                    "runtime_config": {"dialogue_model_effort": "high"},
                }
            ],
        }
    )

    assert changed is True
    assert payload["version"] == 5
    role = payload["roles"][0]
    assert role["profile"]["character"]["profile"] == "背景"
    assert role["runtime_config"] == {"dialogue_model_effort": "high"}

    normalized, changed_again = migrate_manifest_payload(payload)
    assert changed_again is False
    assert normalized == payload


@pytest.mark.parametrize("enabled", [False, True])
def test_v4_moves_novelai_preference_without_changing_other_runtime_keys(enabled):
    original = {
        "version": 4,
        "roles": [
            {
                "id": "mira",
                "runtime_config": {
                    "auto_scene_cg_enabled": enabled,
                    "dialogue_model_effort": "high",
                },
            }
        ],
        "plugin_data": {"other": {"opaque": 42}},
    }
    migrated, changed = migrate_manifest_payload(original)
    assert changed
    assert migrated["plugin_data"]["novelai"] == {
        "mira": {"auto_scene_cg_enabled": enabled}
    }
    assert migrated["plugin_data"]["other"] == {"opaque": 42}
    assert migrated["roles"][0]["runtime_config"] == {"dialogue_model_effort": "high"}
    assert original["roles"][0]["runtime_config"]["auto_scene_cg_enabled"] is enabled
    assert migrate_manifest_payload(migrated) == (migrated, False)


def test_existing_novelai_namespace_is_authoritative_over_legacy_true():
    migrated, _ = migrate_manifest_payload(
        {
            "version": 4,
            "roles": [
                {"id": "mira", "runtime_config": {"auto_scene_cg_enabled": True}}
            ],
            "plugin_data": {"novelai": {"mira": {"auto_scene_cg_enabled": False}}},
        }
    )
    assert migrated["plugin_data"]["novelai"]["mira"]["auto_scene_cg_enabled"] is False
    assert migrated["roles"][0]["runtime_config"] == {}
