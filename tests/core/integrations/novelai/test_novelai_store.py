from __future__ import annotations

import json
from pathlib import Path

from core.integrations.novelai.store import NovelAIStore


def test_list_records_resolves_existing_legacy_workspace_paths(tmp_path: Path) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    store = NovelAIStore(workspace)
    relative_output = Path("2026-07-12") / "record-1" / "output-1.png"
    current_output = workspace / "private_runtime" / "novelai" / "outputs" / relative_output
    current_output.parent.mkdir(parents=True, exist_ok=True)
    current_output.write_bytes(b"png")

    legacy_root = tmp_path / ".akashic" / "workspace" / "private_runtime" / "novelai"
    store._records_path.write_text(
        json.dumps(
            {
                "id": "record-1",
                "created_at": "2026-07-12T15:59:03+00:00",
                "role_id": "role-1",
                "base_image_path": "",
                "output_paths": [str(legacy_root / "outputs" / relative_output)],
            }
        ),
        encoding="utf-8",
    )

    records = store.list_records(role_id="role-1")

    assert records[0]["output_paths"] == [str(current_output)]


def test_list_records_keeps_missing_legacy_paths_unchanged(tmp_path: Path) -> None:
    workspace = tmp_path / ".shiori" / "workspace"
    store = NovelAIStore(workspace)
    legacy_path = (
        tmp_path
        / ".akashic"
        / "workspace"
        / "private_runtime"
        / "novelai"
        / "outputs"
        / "missing.png"
    )
    store._records_path.write_text(
        json.dumps(
            {
                "id": "record-2",
                "created_at": "2026-07-12T15:59:03+00:00",
                "role_id": "role-1",
                "base_image_path": "",
                "output_paths": [str(legacy_path)],
            }
        ),
        encoding="utf-8",
    )

    records = store.list_records(role_id="role-1")

    assert records[0]["output_paths"] == [str(legacy_path)]
