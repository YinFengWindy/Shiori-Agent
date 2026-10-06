"""Installer and model caches stay private without inheriting another uv project."""

from pathlib import Path

from shiori_sdk.managed.paths import native_path
from plugins.sensevoice_asr.backend.runtime_environment import runtime_environment


def test_private_short_environment_overrides_user_uv_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("UV_PROJECT", "unrelated-project")
    monkeypatch.setenv("UV_PYTHON", "unrelated-python")
    monkeypatch.setenv("UV_CACHE_DIR", "unrelated-cache")
    root = tmp_path / "plugin-data/sensevoice_asr/runtime"
    env = runtime_environment(native_path(root), root / "s/123456789abc/p")
    assert "UV_PROJECT" not in env and "UV_PYTHON" not in env
    assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert env["HF_HUB_OFFLINE"] == "1"
    for key, name in (
        ("UV_CACHE_DIR", "u"),
        ("TEMP", "t"),
        ("TMP", "t"),
        ("HF_HOME", "hf"),
    ):
        assert native_path(Path(env[key])) == native_path(root / name)
        assert not env[key].startswith("\\\\?\\")
