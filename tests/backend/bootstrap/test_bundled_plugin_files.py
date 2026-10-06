"""Seed snapshots read only distributable files and reject changing source bytes."""

from pathlib import Path

import pytest

from bootstrap.bundled_plugin_files import stage_bundled_plugin


@pytest.fixture
def package(tmp_path):
    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "manifest.yaml").write_text(
        "package_contract: 1\napi: 2\nid: test_voice\nversion: 0.1.0\n"
        "runtime_api: '>=3.2.0 <4.0.0'\nentry: backend/plugin.py\n"
        "capabilities: []\nassets: [assets/voice.txt]\n",
        encoding="utf-8",
    )
    (source / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    pass\n", encoding="utf-8"
    )
    (source / "assets").mkdir()
    (source / "assets/voice.txt").write_text("voice", encoding="utf-8")
    (source / "README.md").write_text("provider", encoding="utf-8")
    return source


def test_snapshot_does_not_traverse_unselected_development_directories(
    tmp_path, monkeypatch, package
):
    for name in (".venv", "node_modules", "tests", "backend/__pycache__"):
        folder = package / name
        folder.mkdir(parents=True)
        (folder / "private.py").write_text("development only", encoding="utf-8")
    original = Path.iterdir

    def runtime_only(path):
        assert path != package
        assert path.name not in {".venv", "node_modules", "tests", "__pycache__"}
        return original(path)

    monkeypatch.setattr(Path, "iterdir", runtime_only)
    stage = tmp_path / "stage"
    hashes = stage_bundled_plugin(package, stage, "test_voice")
    assert set(hashes) == {
        "manifest.yaml",
        "backend/plugin.py",
        "assets/voice.txt",
        "README.md",
    }
    assert not (stage / ".venv").exists()
    assert (stage / "assets/voice.txt").read_text(encoding="utf-8") == "voice"


def test_snapshot_rejects_a_selected_file_changed_while_reading(
    tmp_path, monkeypatch, package
):
    original = Path.read_bytes

    def changing(path):
        data = original(path)
        if path == package / "README.md":
            path.write_text("changed source bytes", encoding="utf-8")
        return data

    monkeypatch.setattr(Path, "read_bytes", changing)
    with pytest.raises(ValueError, match="复制时变化"):
        stage_bundled_plugin(package, tmp_path / "stage", "test_voice")
