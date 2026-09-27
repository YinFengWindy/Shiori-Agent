"""Explicit SQLite write transactions shared by schema setup and batched writes."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager


@contextmanager
def immediate_transaction(connection: sqlite3.Connection):
    """Run the block in one ``BEGIN IMMEDIATE`` transaction and commit it once.

    Python's legacy transaction control never opens an implicit transaction for
    DDL, so without this every ``CREATE``/``ALTER`` commits (and fsyncs) on its
    own. Any exception rolls the whole block back, leaving no partial schema.
    """

    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
