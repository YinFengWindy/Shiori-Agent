from __future__ import annotations

import json

from core.roles.manifest import RoleManifestRepository


def test_manifest_repository_migrates_legacy_image_and_categories(tmp_path) -> None:
    repository = RoleManifestRepository(tmp_path)
    repository.manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "roles": [
                    {
                        "id": "mira",
                        "name": "Mira",
                        "system_prompt": "fixture",
                        "featured_image": "assets/mira/background.png",
                        "illustrations": ["assets/mira/scene.png"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    role = repository.list_roles()[0]
    persisted = json.loads(repository.manifest_path.read_text(encoding="utf-8"))

    assert role.chat_background == "assets/mira/background.png"
    assert role.asset_categories[0].id == "default"
    assert role.asset_category_bindings == {"assets/mira/scene.png": "default"}
    assert "featured_image" not in persisted["roles"][0]
