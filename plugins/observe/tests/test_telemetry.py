"""Public telemetry reads against data committed by the real observe writer."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sqlite3
import sys
from contextlib import suppress
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


@pytest.fixture
def backend():
    package = Path(__file__).resolve().parents[1] / "backend"
    name = "test_observe_telemetry_backend"
    spec = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    for child in ("telemetry", "events", "writer"):
        importlib.import_module(f"{name}.{child}")
    yield module
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


def test_missing_storage_returns_no_data_without_creating_files(
    tmp_path: Path, backend
):
    workspace = tmp_path / "not-created"
    reader = backend.telemetry.ObserveTelemetry(workspace)
    assert reader.recent_cache_turns("session") == ()
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_real_writer_query_filters_orders_limits_and_preserves_nulls(
    tmp_path: Path, backend
):
    writer = backend.writer.TraceWriter(
        tmp_path / "plugin-data" / "observe" / "observe.db"
    )
    reader = backend.telemetry.ObserveTelemetry(tmp_path)
    task = asyncio.create_task(writer.run())
    try:
        for index in range(35):
            writer.emit(
                backend.events.TurnTrace(
                    source="agent",
                    session_key="selected",
                    user_msg="hi",
                    llm_output=f"reply {index}",
                    react_cache_prompt_tokens=100 + index,
                    react_cache_hit_tokens=None if index == 34 else index,
                )
            )
        writer.emit(
            backend.events.TurnTrace(
                source="agent",
                session_key="another",
                user_msg="hi",
                llm_output="wrong session",
            )
        )
        # TraceWriter stores the source value too; historical non-agent rows must not leak.
        writer.emit(
            backend.events.TurnTrace(
                source="maintenance",
                session_key="selected",
                user_msg="hi",
                llm_output="wrong source",
            )
        )
        await writer.drain()
        turns = reader.recent_cache_turns("selected")
        assert isinstance(turns, tuple)
        assert [turn.reply for turn in turns] == [
            f"reply {index}" for index in range(34, 29, -1)
        ]
        assert turns[0].prompt_tokens == 134
        assert turns[0].hit_tokens is None
        assert turns[0].timestamp
        assert reader.recent_cache_turns("unknown") == ()
        assert len(reader.recent_cache_turns("selected", limit=0)) == 1
        assert len(reader.recent_cache_turns("selected", limit=-8)) == 1
        assert len(reader.recent_cache_turns("selected", limit=100)) == 30
        with pytest.raises(FrozenInstanceError):
            setattr(turns[0], "reply", "mutated")
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def test_reader_opens_existing_database_read_only(tmp_path: Path, backend, monkeypatch):
    path = tmp_path / "plugin-data" / "observe" / "observe.db"
    connection = backend.writer.open_db(path)
    connection.close()
    original_connect = sqlite3.connect

    def assert_read_only(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE unexpected_write (id INTEGER)")
        return connection

    monkeypatch.setattr(sqlite3, "connect", assert_read_only)
    assert (
        backend.telemetry.ObserveTelemetry(tmp_path).recent_cache_turns("session") == ()
    )


def test_storage_errors_preserve_the_sqlite_cause(tmp_path: Path, backend):
    path = tmp_path / "plugin-data" / "observe" / "observe.db"
    path.parent.mkdir(parents=True)
    _ = path.write_bytes(b"not a database")
    with pytest.raises(OSError, match="读取 KVCache") as error:
        backend.telemetry.ObserveTelemetry(tmp_path).recent_cache_turns("session")
    assert isinstance(error.value.__cause__, sqlite3.Error)
