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
    assert role["proactive"]["candidates"] == [
        {"channel": "qq", "chat_id": "gqq:831907794"}
    ]
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

    # Contacts normalize before comparing, so these stay private (and lose
    # their contact list in the v8 step).
    assert migrated["roles"][0]["channel_bindings"] == [
        {"channel": "qq", "chat_id": "123", "chat_type": "private"},
        {"channel": "qq", "chat_id": "456", "chat_type": "private"},
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
    assert joye["proactive"]["candidates"] == [{"channel": "qq", "chat_id": "gqq:7"}]
    assert mira["proactive"]["candidates"] == [{"channel": "qq", "chat_id": "8"}]


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
    assert migrated["version"] == CURRENT_MANIFEST_VERSION == 9
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
            "chat_type": "group",
            "blocked_senders": [],
        }
    ]


def test_v6_prefixes_bare_qqbot_chat_ids_and_their_proactive_target() -> None:
    migrated, changed = migrate_manifest_payload(
        {
            "version": 6,
            "roles": [
                {
                    "id": "mira",
                    "profile": {},
                    "channel_bindings": [
                        # The transport read a kind-less ID as C2C.
                        {"channel": "qqbot", "chat_id": "OPENID", "allow_from": ["u"]},
                        {
                            "channel": "qqbot",
                            "chat_id": "qqbot:OLD",
                            "allow_from": ["u"],
                        },
                        {
                            "channel": "qqbot",
                            "chat_id": "c2c:KEEP",
                            "allow_from": ["u"],
                        },
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qqbot",
                        "target_chat_id": "OPENID",
                    },
                }
            ],
        }
    )

    assert changed is True
    role = migrated["roles"][0]
    assert [
        (item["chat_id"], item["chat_type"]) for item in role["channel_bindings"]
    ] == [("c2c:OPENID", "private"), ("c2c:OLD", "private"), ("c2c:KEEP", "private")]
    assert role["proactive"]["candidates"] == [
        {"channel": "qqbot", "chat_id": "c2c:OPENID"}
    ]
    assert migrate_manifest_payload(migrated) == (migrated, False)


def test_v6_keeps_proactive_target_of_other_channels_with_the_same_id() -> None:
    migrated, _ = migrate_manifest_payload(
        {
            "version": 6,
            "roles": [
                {
                    "id": "mira",
                    "profile": {},
                    "channel_bindings": [
                        {"channel": "qqbot", "chat_id": "42", "allow_from": ["u"]},
                        {"channel": "telegram", "chat_id": "42", "allow_from": ["u"]},
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "telegram",
                        "target_chat_id": "42",
                    },
                }
            ],
        }
    )

    assert migrated["roles"][0]["proactive"]["candidates"] == [
        {"channel": "telegram", "chat_id": "42"}
    ]


def test_v7_replaces_contact_whitelists_with_group_blacklists() -> None:
    migrated, changed = migrate_manifest_payload(
        {
            "version": 7,
            "roles": [
                {
                    "id": "mira",
                    "profile": {},
                    "channel_bindings": [
                        {
                            "channel": "qq",
                            "chat_id": "3",
                            "chat_type": "private",
                            "allow_from": ["3"],
                        },
                        {
                            "channel": "qq",
                            "chat_id": "gqq:7",
                            "chat_type": "group",
                            "allow_from": ["3"],
                        },
                        {
                            "channel": "desktop",
                            "chat_id": "role:mira",
                            "chat_type": "private",
                            "allow_from": [],
                        },
                    ],
                }
            ],
        }
    )

    assert changed is True
    # The old sole contact was the one member let in; it must not become
    # blacklisted, so every group starts with an empty blacklist.
    assert migrated["roles"][0]["channel_bindings"] == [
        {"channel": "qq", "chat_id": "3", "chat_type": "private"},
        {
            "channel": "qq",
            "chat_id": "gqq:7",
            "chat_type": "group",
            "blocked_senders": [],
        },
        {"channel": "desktop", "chat_id": "role:mira", "chat_type": "private"},
    ]
    assert migrate_manifest_payload(migrated) == (migrated, False)


def test_v9_manifest_is_left_untouched() -> None:
    payload = {
        "version": 9,
        "roles": [
            {
                "id": "mira",
                "profile": {},
                "channel_bindings": [
                    {
                        "channel": "qq",
                        "chat_id": "gqq:7",
                        "chat_type": "group",
                        "blocked_senders": ["42"],
                    }
                ],
            }
        ],
    }

    assert migrate_manifest_payload(payload) == (payload, False)


def test_v8_target_and_desktop_become_the_candidates() -> None:
    migrated, changed = migrate_manifest_payload(
        {
            "version": 8,
            "roles": [
                {
                    "id": "mira",
                    "profile": {},
                    "channel_bindings": [
                        {"channel": "desktop", "chat_id": "role:mira"},
                        {"channel": "qq", "chat_id": "10001"},
                        {"channel": "qq", "chat_id": "gqq:7"},
                    ],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qq",
                        "target_chat_id": "gqq:7",
                        "profile": "quiet",
                    },
                },
                {
                    "id": "luna",
                    "profile": {},
                    # A stale target naming no binding is dropped; the user's
                    # enabled setting remains available for account selection.
                    "channel_bindings": [{"channel": "telegram", "chat_id": "42"}],
                    "proactive": {
                        "enabled": True,
                        "target_channel": "qq",
                        "target_chat_id": "9",
                    },
                },
                {
                    "id": "nova",
                    "profile": {},
                    "channel_bindings": [
                        {"channel": "desktop", "chat_id": "role:nova"}
                    ],
                },
            ],
        }
    )

    assert changed is True
    mira, luna, nova = migrated["roles"]
    assert mira["proactive"] == {
        "enabled": True,
        "profile": "quiet",
        "candidates": [
            {"channel": "desktop", "chat_id": "role:mira"},
            {"channel": "qq", "chat_id": "gqq:7"},
        ],
    }
    assert luna["proactive"] == {"enabled": True, "candidates": []}
    assert nova["proactive"] == {
        "candidates": [{"channel": "desktop", "chat_id": "role:nova"}]
    }
    assert migrate_manifest_payload(migrated) == (migrated, False)
