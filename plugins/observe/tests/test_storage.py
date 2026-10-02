"""Observe requests only migrations for the two files it owns."""

from plugins.observe.backend.storage import prepare_storage
from shiori_sdk.testing.memory import FakeMemoryStorage


def test_migrates_only_owned_database_and_retention_marker(tmp_path):
    requests = []
    destination = tmp_path / "owner-selected"

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            requests.append((workspace, plugin_id, name, source))
            return destination / name

    assert prepare_storage(tmp_path, Storage()) == destination / "observe.db"
    assert requests == [
        (tmp_path, "observe", name, tmp_path / "observe" / name)
        for name in ("observe.db", ".last_cleanup")
    ]
