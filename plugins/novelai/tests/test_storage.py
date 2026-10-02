"""Plugin path normalization honors the migration owner's returned destination."""

import json
from shiori_sdk.testing.memory import FakeMemoryStorage
from plugins.novelai.backend.storage import storage_root


def test_normalization_uses_explicit_storage_destination(tmp_path):
    root = tmp_path / "selected-owner-root"
    root.mkdir()
    old = tmp_path / "private_runtime/novelai"
    record = {"output_paths": [str(old / "outputs/image.png")], "base_image_path": ""}
    (root / "records.jsonl").write_text(json.dumps(record), encoding="utf-8")

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            assert source == old and plugin_id == "novelai"
            return root

    assert storage_root(tmp_path, Storage()) == root
    normalized = json.loads((root / "records.jsonl").read_text(encoding="utf-8"))
    assert normalized["output_paths"] == [str(root / "outputs/image.png")]
    assert normalized["original_output_paths"] == record["output_paths"]


def test_normalization_rewrites_meta_and_runs_once(tmp_path):
    """Moved records and their meta follow the new root; a rerun changes nothing."""
    old = tmp_path / "private_runtime/novelai"
    root = tmp_path / "plugin-root"
    output = root / "outputs/record/output.png"
    output.parent.mkdir(parents=True)
    record = {
        "output_paths": [str(old / "outputs/record/output.png")],
        "base_image_path": str(old / "outputs/record/base.png"),
    }
    (root / "records.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (output.parent / "meta.json").write_text(json.dumps(record), encoding="utf-8")

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            return root

    assert storage_root(tmp_path, Storage()) == root
    migrated = json.loads((root / "records.jsonl").read_text(encoding="utf-8"))
    assert migrated["output_paths"] == [str(output)]
    assert migrated["base_image_path"] == str(root / "outputs/record/base.png")
    meta = json.loads((output.parent / "meta.json").read_text(encoding="utf-8"))
    assert meta == migrated

    rerun = {**migrated, "base_image_path": str(old / "late.png")}
    (root / "records.jsonl").write_text(json.dumps(rerun) + "\n", encoding="utf-8")
    assert storage_root(tmp_path, Storage()) == root
    assert json.loads((root / "records.jsonl").read_text(encoding="utf-8")) == rerun
