"""Retention cancellation must join its SQLite worker before disposal returns."""

import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

from plugins.observe.backend import retention
from plugins.observe.backend.db import open_db


@pytest.mark.asyncio
async def test_cancellation_waits_until_worker_closes_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "observe.db"
    open_db(db_path).close()
    started = asyncio.Event()
    release = threading.Event()
    opened: list[sqlite3.Connection] = []
    loop = asyncio.get_running_loop()

    def blocked_open(path: Path):
        conn = open_db(path)
        opened.append(conn)
        _ = loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5), "test worker was not released"
        return conn

    monkeypatch.setattr(retention, "open_db", blocked_open)
    task = asyncio.create_task(retention.run_retention_if_needed(db_path))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        _ = task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done(), "cancel must wait for the SQLite worker"
    finally:
        release.set()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(opened) == 1
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                _ = opened[0].execute("SELECT 1")
        finally:
            # Clean up the worker even when checking the old implementation fails.
            await loop.shutdown_default_executor()
