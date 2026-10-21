from core.roles.migration import CURRENT_MANIFEST_VERSION, migrate_manifest_payload
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
    assert payload["version"] == CURRENT_MANIFEST_VERSION
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


def test_current_manifest_is_left_untouched() -> None:
    payload = {
        "version": CURRENT_MANIFEST_VERSION,
        "roles": [
            {
                "id": "mira",
                "profile": {},
                "proactive": {"enabled": True, "candidates": []},
            }
        ],
    }

    assert migrate_manifest_payload(payload) == (payload, False)


@pytest.mark.parametrize("version", [9, CURRENT_MANIFEST_VERSION])
@pytest.mark.parametrize("legacy_enabled", [False, True])
@pytest.mark.parametrize("current_enabled", [None, False, True])
def test_natural_chat_moves_to_builtin_without_overwriting_new_choice(
    version, legacy_enabled, current_enabled
):
    runtime = {"dialogue_model_effort": "high"}
    if current_enabled is not None:
        runtime["natural_chat_enabled"] = current_enabled
    original = {
        "version": version,
        "roles": [{"id": "mira", "runtime_config": runtime}, {"id": "new"}],
        "plugin_data": {
            "natural_chat": {"mira": {"enabled": legacy_enabled}},
            "other": {"opaque": 42},
        },
    }
    migrated, changed = migrate_manifest_payload(original)
    assert changed
    assert migrated["roles"][0]["runtime_config"] == {
        "dialogue_model_effort": "high",
        "natural_chat_enabled": (
            legacy_enabled if current_enabled is None else current_enabled
        ),
    }
    assert "natural_chat_enabled" not in migrated["roles"][1].get("runtime_config", {})
    assert migrated["plugin_data"] == {"other": {"opaque": 42}}
    assert original["plugin_data"]["natural_chat"]["mira"]["enabled"] is legacy_enabled
    assert migrate_manifest_payload(migrated) == (migrated, False)
