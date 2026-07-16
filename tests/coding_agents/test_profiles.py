from decimal import Decimal

import pytest

from coding_agents.models import PermissionLevel, Provider
from coding_agents.profiles import (
    ModelProfile,
    ProfileEffort,
    ProfileError,
    ProfileRegistry,
)


def _profiles():
    return {
        "codex_fast": {
            "provider": "codex",
            "model": "configured-codex-model",
            "effort": "medium",
            "timeout_seconds": 1800,
            "max_permission_level": "workspace-write",
        },
        "claude_deep": {
            "provider": "claude",
            "model": "configured-claude-model",
            "effort": "high",
            "timeout_seconds": 3600,
            "max_budget_usd": 20,
        },
    }


def test_mapping_loads_named_profiles_without_hardcoded_model_names():
    registry = ProfileRegistry.from_mapping(
        _profiles(), default_profile_id="codex_fast"
    )

    codex = registry.get("codex_fast")
    claude = registry.get("claude_deep")

    assert codex.provider is Provider.CODEX
    assert codex.model == "configured-codex-model"
    assert claude.provider is Provider.CLAUDE
    assert claude.max_budget_usd == Decimal("20")


def test_selection_order_is_explicit_then_skill_then_default():
    registry = ProfileRegistry.from_mapping(
        _profiles(), default_profile_id="codex_fast"
    )

    assert (
        registry.select(
            explicit_profile_id="claude_deep", skill_profile_id="codex_fast"
        ).profile_id
        == "claude_deep"
    )
    assert registry.select(skill_profile_id="claude_deep").profile_id == "claude_deep"
    assert registry.select().profile_id == "codex_fast"


def test_explicit_missing_profile_does_not_fallback_to_default():
    registry = ProfileRegistry.from_mapping(
        _profiles(), default_profile_id="codex_fast"
    )

    with pytest.raises(ProfileError) as error:
        registry.select(explicit_profile_id="missing")

    assert error.value.code == "profile_not_found"


def test_snapshot_enforces_permission_ceiling_and_freezes_cli_version():
    registry = ProfileRegistry.from_mapping(_profiles())
    snapshot = registry.snapshot(
        "codex_fast",
        permission_level=PermissionLevel.WORKSPACE_WRITE,
        cli_version="codex-cli 1.2.3",
    )

    assert snapshot.permission_level is PermissionLevel.WORKSPACE_WRITE
    assert snapshot.cli_version == "codex-cli 1.2.3"

    with pytest.raises(ProfileError) as error:
        registry.snapshot(
            "codex_fast",
            permission_level=PermissionLevel.FULL_ACCESS,
            cli_version="codex-cli 1.2.3",
        )

    assert error.value.code == "permission_denied"


def test_codex_rejects_claude_only_budget_field():
    payload = _profiles()
    payload["codex_fast"]["max_budget_usd"] = 5

    with pytest.raises(ProfileError) as error:
        ProfileRegistry.from_mapping(payload)

    assert error.value.code == "profile_invalid"


def test_profile_command_cannot_override_provider_executable():
    payload = _profiles()
    payload["codex_fast"]["command"] = "custom-codex --unsafe"

    with pytest.raises(ProfileError) as error:
        ProfileRegistry.from_mapping(payload)

    assert error.value.code == "profile_invalid"


def test_profile_accepts_config_default_command_equal_to_provider():
    payload = _profiles()
    payload["codex_fast"]["command"] = "codex"
    payload["claude_deep"]["command"] = "claude"

    registry = ProfileRegistry.from_mapping(payload)

    assert registry.get("codex_fast").provider is Provider.CODEX
    assert registry.get("claude_deep").provider is Provider.CLAUDE


@pytest.mark.parametrize(
    ("provider", "effort"),
    [("codex", "xhigh"), ("claude", "max")],
)
def test_provider_specific_high_effort_is_supported(provider, effort):
    payload = {
        "profile": {
            "provider": provider,
            "model": "model",
            "effort": effort,
            "timeout_seconds": 60,
        }
    }

    profile = ProfileRegistry.from_mapping(payload).get("profile")

    assert profile.effort.value == effort
    assert profile.max_permission_level is PermissionLevel.WORKSPACE_WRITE


@pytest.mark.parametrize(
    ("provider", "effort"),
    [("codex", "max"), ("claude", "xhigh")],
)
def test_provider_specific_effort_mismatch_is_rejected(provider, effort):
    payload = {
        "profile": {
            "provider": provider,
            "model": "model",
            "effort": effort,
            "timeout_seconds": 60,
        }
    }

    with pytest.raises(ProfileError) as error:
        ProfileRegistry.from_mapping(payload)

    assert error.value.code == "profile_invalid"


@pytest.mark.parametrize(
    "override",
    [
        {"timeout_seconds": 0},
        {"max_parallel_runs": 0},
        {"unknown": True},
        {"effort": "extreme"},
    ],
)
def test_invalid_profile_configuration_fails_fast(override):
    payload = {"profile": {**_profiles()["claude_deep"], **override}}

    with pytest.raises(ProfileError) as error:
        ProfileRegistry.from_mapping(payload)

    assert error.value.code == "profile_invalid"


def test_duplicate_profile_ids_are_rejected():
    profile = ModelProfile(
        profile_id="same",
        provider=Provider.CODEX,
        model="model",
        effort=ProfileEffort.MEDIUM,
        timeout_seconds=60,
    )

    with pytest.raises(ProfileError) as error:
        ProfileRegistry([profile, profile])

    assert error.value.code == "profile_invalid"
