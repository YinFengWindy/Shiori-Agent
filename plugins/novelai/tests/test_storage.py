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
