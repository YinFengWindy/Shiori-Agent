from core.roles.profile_models import RoleProfile


def test_role_profile_round_trips_runtime_fields_without_source_noise() -> None:
    profile = RoleProfile.from_dict(
        {
            "version": 1,
            "character": {
                "profile": "海边的向导",
                "personality": "温柔",
                "behavior_rules": "回答简洁",
            },
            "greetings": {"default": "你好", "alternates": ["晚上好"]},
            "knowledge_base": {"enabled": True, "token_budget": 10, "entries": []},
            "source": {"creator": "discarded"},
            "compatibility": {"unsupported_rules": ["discarded"]},
        }
    )

    serialized = profile.to_dict()
    assert serialized["character"]["behavior_rules"] == "回答简洁"
    assert "greetings" not in serialized
    assert "source" not in serialized
    assert "compatibility" not in serialized
    assert "response_constraints" not in serialized
    assert "knowledge_base" not in serialized


def test_legacy_fields_are_mapped_to_profile() -> None:
    profile = RoleProfile.from_legacy(system_prompt="规则", background="背景")

    assert profile.character.profile == "背景"
    assert profile.character.behavior_rules == "规则"
    assert profile.character.response_constraints == ""


def test_profile_round_trips_constraints_nickname_and_attribution() -> None:
    provenance = {
        "format": "charx",
        "card_version": "3.0",
        "creator": "作者",
        "tags": ["科幻"],
        "source": ["https://example.test/card"],
        "created_at": 123,
        "updated_at": "2026-09-01",
        "imported_at": "2026-09-07",
    }
    profile = RoleProfile.from_dict(
        {
            "character": {"response_constraints": "每次回答一句", "nickname": "小栞"},
            "import_provenance": provenance,
        }
    )

    assert profile.to_dict()["import_provenance"] == provenance
    assert profile.character.nickname == "小栞"
    assert profile.character.response_constraints == "每次回答一句"
