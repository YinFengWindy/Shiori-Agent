from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.roles import RoleStore
from core.roles import assets as assets_module


def test_new_unbound_role_remains_unbound_when_models_are_added(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    restarted = RoleStore(tmp_path)
    assert restarted.migrate_model_selections(dialogue_registration_id="new-model") == 0
    assert (
        restarted.get_role("mira").runtime_config["dialogue_model_registration_id"]
        == ""
    )


def test_selection_migration_only_fills_missing_legacy_fields(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.update_role("mira", runtime_config={"old_setting": True})
    assert store.migrate_model_selections(dialogue_registration_id="first") == 2
    assert store.migrate_model_selections(dialogue_registration_id="second") == 0
    store.update_role(
        "mira", runtime_config={"dialogue_model_registration_id": "deleted"}
    )
    store.migrate_model_selections(dialogue_registration_id="second")
    assert (
        store.get_role("mira").runtime_config["dialogue_model_registration_id"]
        == "deleted"
    )


def test_new_roles_stay_unbound_after_model_selection_migration(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.migrate_model_selections(dialogue_registration_id="new-model")
    next_role = store.create_role(name="Next", system_prompt="next")
    assert next_role.runtime_config["dialogue_model_registration_id"] == ""
    assert store.get_role("mira").runtime_config["dialogue_model_registration_id"] == ""


def test_explicit_model_binding_is_persisted(tmp_path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        name="Mira",
        system_prompt="mira",
        runtime_config={
            "dialogue_model_registration_id": "selected-model",
        },
    )
    assert (
        RoleStore(tmp_path)
        .get_role(role.id)
        .runtime_config["dialogue_model_registration_id"]
        == "selected-model"
    )


@pytest.mark.parametrize("failure_phase", ["copy", "manifest"])
@pytest.mark.parametrize("preexisting_directory", [False, True])
def test_failed_role_creation_cleans_only_its_own_imported_assets(
    tmp_path, monkeypatch, failure_phase, preexisting_directory
):
    store = RoleStore(tmp_path)
    store.create_role(name="Existing", system_prompt="existing", role_id="existing")
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    directory = store.assets_dir / "new-role"
    if preexisting_directory:
        directory.mkdir()
        (directory / "unrelated.png").write_bytes(b"keep")
    original_copy = assets_module.shutil.copy2
    original_save = store._save_roles
    copies = 0

    def fail_second_copy(source_path, target):
        nonlocal copies
        copies += 1
        if copies == 2:
            Path(target).write_bytes(b"partial")
            raise PermissionError("copy unavailable")
        return original_copy(source_path, target)

    def fail_manifest(_roles):
        raise PermissionError("manifest unavailable")

    if failure_phase == "copy":
        monkeypatch.setattr(assets_module.shutil, "copy2", fail_second_copy)
    else:
        monkeypatch.setattr(store, "_save_roles", fail_manifest)
    with pytest.raises(PermissionError, match=f"{failure_phase} unavailable"):
        store.create_role(
            name="New",
            system_prompt="new",
            role_id="new-role",
            avatar_source=source,
            illustration_sources=[source],
        )
    assert [role.id for role in store.list_roles()] == ["existing"]
    if preexisting_directory:
        assert [path.name for path in directory.iterdir()] == ["unrelated.png"]
        assert (directory / "unrelated.png").read_bytes() == b"keep"
    else:
        assert not directory.exists()
    monkeypatch.setattr(assets_module.shutil, "copy2", original_copy)
    monkeypatch.setattr(store, "_save_roles", original_save)
    assert store.create_role(
        name="New", system_prompt="new", role_id="new-role", avatar_source=source
    ).avatar


def test_profile_update_persists_constraints_without_rewriting_legacy_background(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira", system_prompt="旧规则", background="旧背景", role_id="mira"
    )

    store.update_role(
        "mira",
        profile={
            "character": {
                "profile": "新资料",
                "behavior_rules": "新规则",
                "response_constraints": "新约束",
            },
            "knowledge_base": {"enabled": True, "token_budget": 1},
        },
    )
    reloaded = store.get_role("mira")

    assert reloaded is not None
    assert reloaded.background == "旧背景"
    assert reloaded.profile.character.profile == "新资料"
    assert reloaded.profile.character.response_constraints == "新约束"
    assert reloaded.profile.knowledge_base.enabled is True
    assert "token_budget" not in reloaded.to_dict()["profile"]["knowledge_base"]


def test_structured_profile_can_clear_rules_without_legacy_validation_or_background_write(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira", system_prompt="旧规则", background="旧背景", role_id="mira"
    )

    store.update_role(
        "mira",
        system_prompt="",
        background="不应保存的旧表单值",
        profile={
            "character": {
                "profile": "资料",
                "behavior_rules": "",
                "response_constraints": "约束",
            }
        },
    )

    reloaded = store.get_role("mira")
    assert reloaded is not None
    assert reloaded.background == "旧背景"
    assert reloaded.profile.character.behavior_rules == ""
    assert reloaded.profile.character.profile == "资料"
    assert reloaded.profile.character.response_constraints == "约束"

    with pytest.raises(ValueError, match="role.system_prompt"):
        store.update_role("mira", system_prompt="")


def test_role_store_raises_for_corrupted_manifest(tmp_path):
    store = RoleStore(tmp_path)
    store.manifest_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        store.list_roles()


def test_role_store_rejects_invalid_manifest_shape(tmp_path):
    store = RoleStore(tmp_path)
    store.manifest_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="角色清单格式无效"):
        store.list_roles()


def test_role_store_persists_proactive_policy_and_keeps_it_when_candidates_go(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.update_role(
        "mira",
        channel_bindings=[
            {
                "channel": "telegram",
                "chat_id": "42",
                "chat_type": "private",
            },
        ],
        proactive={
            "enabled": True,
            "candidates": [{"channel": "telegram", "chat_id": "42"}],
            "profile": "quiet",
            "overrides": {"gate": {"judge_send_threshold": 0.8}},
            "agent": {"model": "agent-model", "max_steps": 12},
            "drift": {"enabled": True, "min_interval_hours": 6},
        },
    )

    updated = store.update_role("mira", channel_bindings=[])
    reloaded = store.get_role("mira")

    assert updated.proactive.enabled is False
    assert updated.proactive.candidates == ()
    assert reloaded is not None
    assert reloaded.proactive.profile == "quiet"
    assert "model" not in reloaded.proactive.agent
    assert reloaded.proactive.agent["max_steps"] == 12
    assert reloaded.proactive.drift["min_interval_hours"] == 6
    assert reloaded.proactive.policy_configured is True
