"""Engine startup diagnostics must leave the desktop bridge's stdout untouched."""

import logging
from pathlib import Path

import pytest

from plugins.akasha.backend import core
from plugins.akasha.backend.engine import AkashaMemoryEngine
from plugins.akasha.backend.store import AkashaStore
from session.store import SessionStore


@pytest.mark.parametrize("build_fails", [False, True])
def test_idf_startup_reports_through_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    build_fails: bool,
):
    sessions_path = tmp_path / "sessions.db"
    sessions = SessionStore(sessions_path)
    sessions.close()
    store = AkashaStore(tmp_path / "akasha.db")
    engine = object.__new__(AkashaMemoryEngine)
    engine._session_db_path = sessions_path
    engine._store = store

    def build_idf(*_args: object):
        if build_fails:
            raise RuntimeError("IDF test failure")
        return {"example": 1.0}

    # Diagnostics must not depend on the tokenizer's first-import behavior.
    monkeypatch.setattr(core, "build_idf_table", build_idf)
    caplog.set_level(logging.INFO, logger="plugins.akasha.backend.engine")
    try:
        engine._ensure_idf_table()
    finally:
        store.close()

    assert capsys.readouterr().out == ""
    expected = "IDF test failure" if build_fails else "built FTS IDF table: 1 tokens"
    assert expected in caplog.text
