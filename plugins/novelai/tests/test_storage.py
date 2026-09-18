"""Legacy generated assets and exact requests migrate together."""

import json
from pathlib import Path

from plugins.novelai.backend.storage import storage_root


def test_generation_migration_normalizes_records_and_retains_legacy_identity(
    tmp_path: Path,
):
    old = tmp_path / "private_runtime/novelai"
    output = old / "outputs/record/output.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"image")
    record = {"id": "record", "output_paths": [str(output)], "base_image_path": ""}
    (old / "records.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (output.parent / "meta.json").write_text(json.dumps(record), encoding="utf-8")
    (output.parent / "request.json").write_text(
        '{"parameters":{"seed":12}}', encoding="utf-8"
    )
    root = storage_root(tmp_path)
    migrated = json.loads((root / "records.jsonl").read_text(encoding="utf-8"))
    assert migrated["original_output_paths"] == [str(output)]
    assert migrated["output_paths"] == [str(root / "outputs/record/output.png")]
    assert Path(migrated["output_paths"][0]).read_bytes() == b"image"
    assert (root / "outputs/record/request.json").read_text(
        encoding="utf-8"
    ) == '{"parameters":{"seed":12}}'
    assert output.is_file()
    assert storage_root(tmp_path) == root
