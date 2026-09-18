"""Live database leases guard migration across overlapping runtimes."""

import sqlite3

import pytest

from infra.persistence.sqlite_lifecycle import (
    open_owned_database,
    require_inactive_data,
)


def test_connection_holds_lease_until_idempotent_close(tmp_path):
    source = tmp_path / "memory.db"
    connection = open_owned_database(source)
    with pytest.raises(RuntimeError, match="请重启"):
        with require_inactive_data(source):
            pass
    connection.close()
    connection.close()
    with require_inactive_data(source):
        pass


def test_failed_open_does_not_retain_lease(tmp_path):
    source = tmp_path / "missing/memory.db"
    with pytest.raises(sqlite3.OperationalError):
        open_owned_database(source)
    with require_inactive_data(source):
        pass
