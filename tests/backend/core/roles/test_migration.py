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


def test_v5_keeps_private_qq_binding_with_unnormalized_contacts() -> None:
    bindings = [
        {"channel": "qq", "chat_id": "123", "allow_from": ["123", "123"]},
        {"channel": "qq", "chat_id": "456", "allow_from": [" 456", ""]},
    ]
    migrated, _ = migrate_manifest_payload(
        {
            "version": 5,
            "roles": [{"id": "mira", "profile": {}, "channel_bindings": bindings}],
        }
    )

    # Contacts normalize like RoleChannelBindingConfig, so these stay private.
    assert migrated["roles"][0]["channel_bindings"] == [
        {**binding, "chat_type": "private"} for binding in bindings
    ]


def test_v5_prefixes_bare_proactive_target_of_existing_gqq_group_binding() -> None:
    migrated, _ = migrate_manifest_payload(
        {
            "version": 5,
            "roles": [
                {
                    "id": "joye",
                    "profile": {},
                    # The old bare==gqq equivalence let this pair be saved.
                    "channel_bindings": [
                        {"channel": "qq", "chat_id": "gqq:7", "allow_from": ["3"]},
                        {"channel": "qq", "chat_id": "8", "allow_from": ["8"]},
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qq",
                        "target_chat_id": "7",
                    },
                },
                {
                    "id": "mira",
                    "profile": {},
                    # A bare target that is itself a bound private chat stays.
                    "channel_bindings": [
                        {"channel": "qq", "chat_id": "gqq:8", "allow_from": ["8"]},
                        {"channel": "qq", "chat_id": "8", "allow_from": ["8"]},
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qq",
                        "target_chat_id": "8",
                    },
                },
            ],
        }
    )

    joye, mira = migrated["roles"]
    assert joye["channel_bindings"][0]["chat_id"] == "gqq:7"
    assert joye["proactive"]["target_chat_id"] == "gqq:7"
    assert mira["proactive"]["target_chat_id"] == "8"


def test_v6_fills_chat_type_from_legacy_chat_id_formats() -> None:
    migrated, changed = migrate_manifest_payload(
        {
            "version": 6,
            "roles": [
                {
                    "id": "mira",
                    "profile": {},
                    "channel_bindings": [
                        {"channel": "qq", "chat_id": "gqq:7", "allow_from": ["3"]},
                        {"channel": "qq", "chat_id": "3", "allow_from": ["3"]},
                        {
                            "channel": "telegram",
                            "chat_id": "-1001",
                            "allow_from": ["a"],
                        },
                        {"channel": "telegram", "chat_id": "42", "allow_from": ["a"]},
                        {"channel": "qqbot", "chat_id": "c2c:u", "allow_from": ["u"]},
                        {"channel": "feishu", "chat_id": "oc_1", "allow_from": ["ou"]},
                        {
                            "channel": "desktop",
                            "chat_id": "role:mira",
                            "allow_from": [],
                        },
                    ],
                }
            ],
        }
    )

    assert changed is True
    assert migrated["version"] == CURRENT_MANIFEST_VERSION == 7
    assert [
        (item["channel"], item["chat_type"])
        for item in migrated["roles"][0]["channel_bindings"]
    ] == [
        ("qq", "group"),
        ("qq", "private"),
        ("telegram", "group"),
        ("telegram", "private"),
        ("qqbot", "private"),
        ("feishu", "private"),
        ("desktop", "private"),
    ]
    assert migrate_manifest_payload(migrated) == (migrated, False)


def test_v5_group_rewritten_to_gqq_is_typed_as_group() -> None:
    migrated, _ = migrate_manifest_payload(
        {
            "version": 5,
            "roles": [
                {
                    "id": "joye",
                    "profile": {},
                    "channel_bindings": [
                        {"channel": "qq", "chat_id": "831907794", "allow_from": ["3"]}
                    ],
                }
            ],
        }
    )

    assert migrated["roles"][0]["channel_bindings"] == [
        {
            "channel": "qq",
            "chat_id": "gqq:831907794",
            "allow_from": ["3"],
            "chat_type": "group",
        }
    ]
