from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from infra.persistence.json_store import atomic_save_json, load_json, save_json


def test_load_json_returns_default_only_when_file_is_missing(tmp_path: Path):
    path = tmp_path / "missing.json"

    assert load_json(path, default={"missing": True}) == {"missing": True}


def test_load_json_raises_for_invalid_json(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")

    with caplog.at_level(logging.ERROR), pytest.raises(json.JSONDecodeError):
        load_json(path, default=[])

    assert "读取 JSON 失败" in caplog.text
    assert str(path) in caplog.text


def test_load_json_raises_for_read_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    path = tmp_path / "protected.json"
    path.write_text("{}", encoding="utf-8")

    def _raise_permission_error(self: Path, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", _raise_permission_error)

    with pytest.raises(PermissionError, match="denied"):
        load_json(path, default={})


def test_json_store_roundtrip_and_write_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    path = tmp_path / "data.json"
    save_json(path, {"text": "中文"})
    assert load_json(path) == {"text": "中文"}

    atomic_save_json(path, {"version": 2})
    assert load_json(path) == {"version": 2}

    class _BadPath:
        parent = tmp_path
        suffix = ".json"

        def with_suffix(self, suffix: str):
            return tmp_path / "bad.json.tmp"

    monkeypatch.setattr(
        Path,
        "write_text",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad")),
    )

    with pytest.raises(RuntimeError, match="bad"):
        save_json(tmp_path / "failed.json", {"value": 1})
    with pytest.raises(RuntimeError, match="bad"):
        atomic_save_json(_BadPath(), {"value": 1})  # type: ignore[arg-type]
