"""Literal substring LIKE patterns ignore SQLite wildcard characters."""

from contextlib import closing
import sqlite3

import pytest

from infra.persistence.sqlite_like import (
    LIKE_ESCAPE_CLAUSE,
    like_contains,
    like_prefix,
)


@pytest.mark.parametrize(
    ("needle", "expected"),
    [
        ("%", ["100% sure", "x\\%y"]),
        ("_", ["snake_case"]),
        ("\\", ["a\\b", "x\\%y"]),
        ("\\%", ["x\\%y"]),
        ("ke_c", ["snake_case"]),
    ],
)
def test_like_contains_matches_special_characters_literally(
    needle: str, expected: list[str]
) -> None:
    rows = ["plain", "100% sure", "snake_case", "a\\b", "x\\%y", "snakeXcase"]
    assert _matching(rows, like_contains(needle)) == expected


def test_like_prefix_matches_literal_prefix_only() -> None:
    rows = ["qq_1:chat", "qqX1:chat", "a:qq_1:chat"]
    assert _matching(rows, like_prefix("qq_1:")) == ["qq_1:chat"]


def _matching(rows: list[str], pattern: str) -> list[str]:
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE t (value TEXT)")
        db.executemany("INSERT INTO t VALUES (?)", [(row,) for row in rows])
        return [
            str(row[0])
            for row in db.execute(
                f"SELECT value FROM t WHERE value LIKE ? {LIKE_ESCAPE_CLAUSE} "
                "ORDER BY rowid",
                (pattern,),
            )
        ]
