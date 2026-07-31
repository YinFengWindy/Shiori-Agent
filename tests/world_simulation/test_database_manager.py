from world_simulation.catalog import WorldCatalog
from world_simulation.database_manager import WorldDatabaseManager


def test_removes_legacy_database_and_sqlite_sidecars(tmp_path):
    legacy_root = tmp_path / "worlds.db"
    for suffix in ("", "-wal", "-shm"):
        (legacy_root.parent / f"{legacy_root.name}{suffix}").write_bytes(b"legacy")

    catalog = WorldCatalog(tmp_path / "worlds" / "catalog.db")
    manager = WorldDatabaseManager(tmp_path, catalog)

    assert not legacy_root.exists()
    assert not (tmp_path / "worlds.db-wal").exists()
    assert not (tmp_path / "worlds.db-shm").exists()

    manager.close()
    catalog.close()
