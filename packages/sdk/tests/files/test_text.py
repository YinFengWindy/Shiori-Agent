"""Atomic text saves preserve UTF-8 and original content on replacement failure."""

from pathlib import Path
import pytest
from shiori_sdk.files.text import atomic_save_text


def test_atomic_save_creates_utf8_file(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    atomic_save_text(path, 'name = "角色"\n')
    assert path.read_bytes() == 'name = "角色"\n'.encode("utf-8")


def test_replace_failure_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("original", encoding="utf-8")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        atomic_save_text(path, "new")
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [path]
