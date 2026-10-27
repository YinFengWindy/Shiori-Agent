import sqlite3
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from shiori_sdk.core.models import MAIN_MODEL, MAIN_PROVIDER
from shiori_sdk.kernel import Kernel
from shiori_sdk.testing.extensions import FakeConfig
from shiori_sdk.testing.memory_context import FakeMemoryPluginContext

from plugins.default_memory.backend.construct import construct_default_engine
from plugins.default_memory.backend.engine import lifecycle
from plugins.default_memory.backend.semantic.store import VEC_DIM


def _context(
    tmp_path: Path,
    values: dict[str, object] | None = None,
    references: dict[str, str] | None = None,
) -> FakeMemoryPluginContext:
    kernel = Kernel()
    kernel.provide(MAIN_PROVIDER, cast(Any, object()))
    kernel.provide(MAIN_MODEL, "chat")
    ctx = FakeMemoryPluginContext(
        tmp_path,
        kernel=kernel,
        inject=("main_provider", "main_model"),
        provides=("memory_engine",),
    )
    config = FakeConfig(values)
    if references:
        config.references.update(references)
    ctx.config = config
    ctx.http = object()
    ctx.light_provider = object()
    ctx.light_model = "light"
    return ctx


def _db(workspace: Path) -> Path:
    return workspace / "plugin-data" / "default_memory" / "memory2.db"


def _seed(path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(sql)
    connection.commit()
    connection.close()


@pytest.mark.parametrize(
    ("values", "references"),
    [
        ({}, None),
        (
            {
                "embedding_api_key": "k",
                "embedding_base_url": "http://embed",
                "embedding_model": "",
            },
            None,
        ),
        # The host resolver returns a reference with no value unchanged.
        (
            {
                "embedding_api_key": "${MISSING}",
                "embedding_base_url": "http://embed",
                "chat_api_key": "chat-secret",
            },
            None,
        ),
    ],
)
def test_missing_credentials_do_not_create_the_database(tmp_path, values, references):
    ctx = _context(tmp_path, values, references)
    with pytest.raises(RuntimeError, match="凭据"):
        construct_default_engine(cast(Any, ctx))
    assert not _db(tmp_path).exists()


def test_resolved_plugin_credential_builds_the_default_engine(tmp_path):
    ctx = _context(
        tmp_path,
        {
            "embedding_api_key": "${EMBED_KEY}",
            "embedding_base_url": "http://embed",
        },
        {"${EMBED_KEY}": "resolved-key"},
    )
    engine = construct_default_engine(cast(Any, ctx))
    try:
        assert engine.describe().name == "default"
        assert engine._embedder is not None
        assert engine._embedder._key == "resolved-key"
    finally:
        if engine._v2_store is not None:
            engine._v2_store.close()


def test_old_database_without_fingerprint_records_the_current_space(tmp_path):
    path = _db(tmp_path)
    _seed(
        path,
        "CREATE TABLE sentinel (note TEXT); INSERT INTO sentinel VALUES ('keep');",
    )
    ctx = _context(
        tmp_path,
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"},
    )
    engine = construct_default_engine(cast(Any, ctx))
    try:
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("SELECT note FROM sentinel").fetchone() == (
                "keep",
            )
            assert connection.execute(
                "SELECT model, dim FROM embedding_fingerprint WHERE id = 1"
            ).fetchone() == ("text-embedding-v3", VEC_DIM)
        finally:
            connection.close()
    finally:
        if engine._v2_store is not None:
            engine._v2_store.close()


def test_vec_dimension_mismatch_keeps_the_declared_sql(tmp_path):
    path = _db(tmp_path)
    _seed(
        path,
        """
        CREATE TABLE sentinel (note TEXT);
        INSERT INTO sentinel VALUES ('keep');
        CREATE TABLE vec_items (embedding float[128]);
        """,
    )
    ctx = _context(
        tmp_path,
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"},
    )
    with pytest.raises(RuntimeError, match="vec_items"):
        construct_default_engine(cast(Any, ctx))
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT note FROM sentinel").fetchone() == ("keep",)
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'vec_items'"
        ).fetchone()[0]
        assert "float[128]" in sql
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'embedding_fingerprint'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()


def test_unparseable_vec_sql_fails_before_writing_a_fingerprint(tmp_path):
    path = _db(tmp_path)
    _seed(path, "CREATE TABLE vec_items (embedding blob);")
    ctx = _context(
        tmp_path,
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"},
    )
    with pytest.raises(RuntimeError, match="无法读取"):
        construct_default_engine(cast(Any, ctx))
    connection = sqlite3.connect(path)
    try:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'embedding_fingerprint'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()


def test_custom_db_path_is_the_database_that_is_checked(tmp_path):
    config_path = tmp_path / "plugin-data" / "default_memory" / "config.local.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('db_path = "custom/mem.db"\n', encoding="utf-8")
    custom = tmp_path / "custom" / "mem.db"
    _seed(
        custom,
        """
        CREATE TABLE sentinel (note TEXT);
        INSERT INTO sentinel VALUES ('keep');
        CREATE TABLE embedding_fingerprint (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            model TEXT NOT NULL,
            dim INTEGER NOT NULL
        );
        INSERT INTO embedding_fingerprint (id, model, dim) VALUES (1, 'other', 32);
        """,
    )
    ctx = _context(
        tmp_path,
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"},
    )
    with pytest.raises(RuntimeError, match="向量空间"):
        construct_default_engine(cast(Any, ctx))
    assert not _db(tmp_path).exists()
    connection = sqlite3.connect(custom)
    try:
        assert connection.execute(
            "SELECT model, dim FROM embedding_fingerprint"
        ).fetchone() == ("other", 32)
    finally:
        connection.close()


async def test_partial_allocation_closes_the_store_when_embedder_fails(
    tmp_path, monkeypatch
):
    ctx = _context(
        tmp_path,
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"},
    )
    store = Mock()
    monkeypatch.setattr(lifecycle, "MemoryStore2", lambda *args, **kwargs: store)
    monkeypatch.setattr(
        lifecycle, "Embedder", Mock(side_effect=ValueError("bad embedding"))
    )
    with pytest.raises(ValueError, match="bad embedding"):
        construct_default_engine(cast(Any, ctx))
    await ctx.aclose()
    store.close.assert_called_once()
