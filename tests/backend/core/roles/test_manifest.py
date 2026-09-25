"""Atomic upgrade coverage at the role persistence boundary."""

import json
from pathlib import Path

import pytest

from core.roles.manifest import RoleManifestRepository
from core.roles.models import RoleRecord


def _legacy(path: Path):
    payload = {
        "version": 3,
        "retained": {"marker": True},
        "roles": [
            {
                "id": "mira",
                "name": "Mira",
                "system_prompt": "test",
                "runtime_config": {"auto_scene_cg_enabled": True},
                "pet_packages": [
                    {
                        "id": "pet",
                        "format": "codex-sprite@1",
                        "display_name": "Pet",
                        "manifest_path": "assets/mira/pets/pet/pet.json",
                        "spritesheet_path": "assets/mira/pets/pet/spritesheet.webp",
                        "imported_at": "today",
                    }
                ],
                "selected_pet_package_id": "pet",
                "desktop_pet_enabled": True,
            }
        ],
        "plugin_data": {"other": {"opaque": 42}},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_disabled_plugin_role_rewrite_captures_legacy_fields_before_projection(
    tmp_path,
):
    repo = RoleManifestRepository(tmp_path)
    original = _legacy(repo.manifest_path)
    # Simulates a caller already holding a projected RoleRecord before its first
    # write in the upgraded app; no plugin setup/import is involved.
    role = RoleRecord.from_dict(original["roles"][0])
    role.name = "Renamed while plugin disabled"
    repo.save_roles([role])
    saved = json.loads(repo.manifest_path.read_text(encoding="utf-8"))
    assert (
        saved.get("plugin_data", {})
        .get("desktop_pet", {})
        .get("mira", {})
        .get("selected_pet_package_id")
        == "pet"
    )
    assert saved["plugin_data"]["desktop_pet"]["mira"]["desktop_pet_enabled"] is True
    assert saved["plugin_data"]["other"] == {"opaque": 42}
    assert saved["plugin_data"]["novelai"]["mira"]["auto_scene_cg_enabled"] is True
    assert saved["retained"] == {"marker": True}
    assert saved["roles"][0]["name"] == role.name
    assert "pet_packages" not in saved["roles"][0]
    assert "auto_scene_cg_enabled" not in saved["roles"][0]["runtime_config"]
    before = repo.manifest_path.read_bytes()
    repo.load_payload()
    assert repo.manifest_path.read_bytes() == before


def test_migration_replace_failure_retains_recoverable_legacy_document(
    tmp_path, monkeypatch
):
    repo = RoleManifestRepository(tmp_path)
    original = _legacy(repo.manifest_path)
    original_replace = Path.replace

    def refuse_replace(path, target):
        if target == repo.manifest_path:
            raise OSError("injected replace failure")
        return original_replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", refuse_replace)
        with pytest.raises(OSError, match="injected replace failure"):
            repo.list_roles()
    assert json.loads(repo.manifest_path.read_text(encoding="utf-8")) == original
    repo.list_roles()
    recovered = repo.load_payload()
    assert (
        recovered["plugin_data"]["desktop_pet"]["mira"]["desktop_pet_enabled"] is True
    )
    assert "pet_packages" not in recovered["roles"][0]
    assert recovered["plugin_data"]["novelai"]["mira"]["auto_scene_cg_enabled"] is True
    assert "auto_scene_cg_enabled" not in recovered["roles"][0]["runtime_config"]


def test_migration_preserves_an_already_captured_namespace(tmp_path):
    repo = RoleManifestRepository(tmp_path)
    original = _legacy(repo.manifest_path)
    # A completed capture is authoritative on retry; stale legacy fields never
    # overwrite a newer plugin-owned choice.
    original["plugin_data"]["desktop_pet"] = {
        "mira": {"pet_packages": [], "desktop_pet_enabled": False}
    }
    repo.manifest_path.write_text(json.dumps(original), encoding="utf-8")
    assert (
        repo.load_payload()["plugin_data"]["desktop_pet"]
        == original["plugin_data"]["desktop_pet"]
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_disabled_novelai_upgrade_survives_ordinary_role_save(tmp_path, enabled):
    from core.roles.store import RoleStore

    roles = RoleStore(tmp_path)
    original = _legacy(roles.manifest_path)
    original["version"] = 4
    original["roles"][0]["runtime_config"]["auto_scene_cg_enabled"] = enabled
    roles.manifest_path.write_text(json.dumps(original), encoding="utf-8")
    roles.update_role("mira", name="Edited while plugin disabled")
    saved = json.loads(roles.manifest_path.read_text(encoding="utf-8"))
    assert saved["plugin_data"]["novelai"]["mira"]["auto_scene_cg_enabled"] is enabled
    assert "auto_scene_cg_enabled" not in saved["roles"][0]["runtime_config"]


def test_legacy_bare_qq_group_binding_is_rewritten_and_persisted_once(tmp_path):
    repo = RoleManifestRepository(tmp_path)
    repo.manifest_path.write_text(
        json.dumps(
            {
                "version": 5,
                "roles": [
                    {
                        "id": "joye",
                        "name": "Joye",
                        "system_prompt": "test",
                        "channel_bindings": [
                            {
                                "channel": "qq",
                                "chat_id": "831907794",
                                "allow_from": ["3174898512"],
                            }
                        ],
                        "proactive": {
                            "enabled": True,
                            "target_channel": "qq",
                            "target_chat_id": "831907794",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    role = repo.list_roles()[0]

    assert role.channel_bindings[0].chat_id == "gqq:831907794"
    assert role.proactive.target_chat_id == "gqq:831907794"
    saved = json.loads(repo.manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == 8
    assert saved["roles"][0]["channel_bindings"][0] == {
        "channel": "qq",
        "chat_id": "gqq:831907794",
        "chat_type": "group",
        "blocked_senders": [],
    }
    assert role.channel_bindings[0].chat_type == "group"
    # The rewrite is persisted, so the next load leaves the file untouched.
    before = repo.manifest_path.read_bytes()
    repo.load_payload()
    assert repo.manifest_path.read_bytes() == before


def test_v7_contact_whitelists_become_empty_blacklists_persisted_once(tmp_path):
    repo = RoleManifestRepository(tmp_path)
    repo.manifest_path.write_text(
        json.dumps(
            {
                "version": 7,
                "roles": [
                    {
                        "id": "joye",
                        "name": "Joye",
                        "system_prompt": "test",
                        "channel_bindings": [
                            {
                                "channel": "qq",
                                "chat_id": "3174898512",
                                "chat_type": "private",
                                "allow_from": ["3174898512"],
                            },
                            {
                                "channel": "qq",
                                "chat_id": "gqq:831907794",
                                "chat_type": "group",
                                "allow_from": ["3174898512"],
                            },
                            {
                                "channel": "desktop",
                                "chat_id": "role:joye",
                                "chat_type": "private",
                                "allow_from": [],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    role = repo.list_roles()[0]

    assert [binding.blocked_senders for binding in role.channel_bindings] == [
        [],
        [],
        [],
    ]
    saved = json.loads(repo.manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == 8
    assert saved["roles"][0]["channel_bindings"] == [
        {"channel": "qq", "chat_id": "3174898512", "chat_type": "private"},
        {
            "channel": "qq",
            "chat_id": "gqq:831907794",
            "chat_type": "group",
            "blocked_senders": [],
        },
        {"channel": "desktop", "chat_id": "role:joye", "chat_type": "private"},
    ]
    before = repo.manifest_path.read_bytes()
    repo.load_payload()
    assert repo.manifest_path.read_bytes() == before
