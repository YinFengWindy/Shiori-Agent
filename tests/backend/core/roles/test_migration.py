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


def test_v5_prefixes_legacy_bare_qq_group_bindings_and_proactive_target() -> None:
    migrated, changed = migrate_manifest_payload(
        {
            "version": 5,
            "roles": [
                {
                    "id": "joye",
                    "profile": {},
                    "channel_bindings": [
                        # Bare ID differing from its sole contact: a legacy group.
                        {"channel": "qq", "chat_id": "831907794", "allow_from": ["3"]},
                        # Bare ID equal to its contact: a private chat, unchanged.
                        {"channel": "qq", "chat_id": "3", "allow_from": ["3"]},
                        {"channel": "telegram", "chat_id": "42", "allow_from": ["a"]},
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qq",
                        "target_chat_id": "831907794",
                    },
                }
            ],
        }
    )

    assert changed is True
    role = migrated["roles"][0]
    assert [item["chat_id"] for item in role["channel_bindings"]] == [
        "gqq:831907794",
        "3",
        "42",
    ]
    assert role["proactive"]["target_chat_id"] == "gqq:831907794"
    assert migrate_manifest_payload(migrated) == (migrated, False)
