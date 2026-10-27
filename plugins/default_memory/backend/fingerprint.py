"""The single-row vector-space fingerprint stored in ``memory2.db``.

Setup writes ``embedding_fingerprint`` (model + dimension) when the file has
none and the declared ``vec_items`` dimension agrees. A mismatch fails setup
without rewriting the row. An older database that has no fingerprint table is
not an error: the first successful setup records the row.
"""

from __future__ import annotations

import re
import sqlite3

_VEC_DIM = re.compile(r"float\[(\d+)\]")

_FINGERPRINT_SQL = """
CREATE TABLE IF NOT EXISTS embedding_fingerprint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    model TEXT NOT NULL,
    dim INTEGER NOT NULL
)
"""


def ensure_embedding_fingerprint(
    connection: sqlite3.Connection, *, model: str, dim: int
) -> None:
    """Record ``model`` / ``dim`` or raise when the existing space differs."""
    declared = _declared_vec_dim(connection)
    stored = _stored_fingerprint(connection)
    if declared is not None and declared != dim:
        raise RuntimeError(
            "default_memory 的向量维度与已有 vec_items 不一致"
            f"（已有 {declared}，当前 {dim}），记忆引擎未启动"
        )
    if stored is not None and stored != (model, dim):
        raise RuntimeError(
            "default_memory 的向量空间与已有记忆库不一致"
            f"（已有 {stored[0]}/{stored[1]}，当前 {model}/{dim}），记忆引擎未启动"
        )
    connection.execute(_FINGERPRINT_SQL)
    if stored is None:
        connection.execute(
            "INSERT INTO embedding_fingerprint (id, model, dim) VALUES (1, ?, ?)",
            (model, dim),
        )
    connection.commit()


def _declared_vec_dim(connection: sqlite3.Connection) -> int | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'vec_items'"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    match = _VEC_DIM.search(str(row[0]))
    if match is None:
        raise RuntimeError(
            "default_memory 无法读取已有 vec_items 的向量维度，记忆引擎未启动"
        )
    return int(match.group(1))


def _stored_fingerprint(connection: sqlite3.Connection) -> tuple[str, int] | None:
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'embedding_fingerprint'"
    ).fetchone()
    if found is None:
        return None
    row = connection.execute(
        "SELECT model, dim FROM embedding_fingerprint WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), int(row[1])
