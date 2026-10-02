"""Observe requests only migrations for the two files it owns."""

from plugins.observe.backend.storage import database_path, prepare_storage
from shiori_sdk.testing.memory import FakeMemoryStorage


def test_migrates_only_owned_database_and_retention_marker(tmp_path):
    requests = []

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            requests.append((workspace, plugin_id, name, source))
            return super().migrate_data(workspace, plugin_id, name, source)

    assert prepare_storage(tmp_path, Storage()) == database_path(tmp_path)
    assert requests == [
        (tmp_path, "observe", name, tmp_path / "observe" / name)
        for name in ("observe.db", ".last_cleanup")
    ]
