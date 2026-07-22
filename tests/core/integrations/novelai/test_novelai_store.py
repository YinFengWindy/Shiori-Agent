from __future__ import annotations

import json
from pathlib import Path

from core.integrations.novelai.store import NovelAIStore


def _write_generation_source(
    store: NovelAIStore,
    *,
    output_path: Path,
    record_id: str = "record-source",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"png")
    (output_path.parent / "request.json").write_text(
        json.dumps(
            {
                "action": "generate",
                "input": "1girl, rainy street",
                "model": "nai-diffusion-4-5-curated",
                "parameters": {
                    "width": 832,
                    "height": 1216,
                    "steps": 24,
                    "sampler": "k_euler_ancestral",
                    "negative_prompt": "blurry",
                    "seed": 17,
                    "reference_image_multiple": ["reference-data"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store._records_path.write_text(
        json.dumps(
            {
                "id": record_id,
                "created_at": "2026-07-22T08:00:00+00:00",
                "role_id": "mira",
                "session_key": "role:mira",
                "mode": "txt2img",
                "prompt": "1girl, rainy street",
                "negative_prompt": "blurry",
                "model": "nai-diffusion-4-5-curated",
                "sampler": "k_euler_ancestral",
                "steps": 24,
                "seed": 17,
                "width": 832,
                "height": 1216,
                "base_image_path": "",
                "output_paths": [str(output_path)],
                "wrote_back_to_role": False,
                "role_asset_paths": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_find_generation_source_by_output_path_loads_exact_request_snapshot(
    tmp_path: Path,
) -> None:
    store = NovelAIStore(tmp_path)
    output_path = (
        tmp_path
        / "private_runtime"
        / "novelai"
        / "outputs"
        / "2026-07-22"
        / "record-source"
        / "output-1.png"
    )
    _write_generation_source(store, output_path=output_path)

    source = store.find_generation_source_by_output_path(str(output_path))

    assert source is not None
    assert source.record.id == "record-source"
    assert source.output_path == str(output_path)
    assert source.request_payload["parameters"]["reference_image_multiple"] == [
        "reference-data"
    ]


def test_find_generation_source_by_output_path_rejects_untracked_image(
    tmp_path: Path,
) -> None:
    store = NovelAIStore(tmp_path)

    assert store.find_generation_source_by_output_path(str(tmp_path / "other.png")) is None


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
