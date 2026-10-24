from __future__ import annotations
import asyncio
import os
import shlex
from pathlib import Path
import pytest
from shiori_sdk.core.tools import ToolCalling
from shiori_sdk.testing.extensions import FakeExtensionContext
from plugins.shell_restore.backend.plugin import setup


def _make_plugin_root(tmp_path: Path) -> Path:
    return tmp_path / "plugins"


def _calling(command: str, tool_name: str = "shell") -> ToolCalling:
    return ToolCalling(
        session_key="",
        channel="",
        chat_id="",
        source="passive",
        call_id="c1",
        tool_name=tool_name,
        arguments={"command": command, "description": "测试命令"},
    )


def _run_shell(root: Path, command: str) -> ToolCalling:
    async def run():
        ctx = FakeExtensionContext("shell_restore", workspace=root.parent / "workspace")
        await setup(ctx)
        result = await ctx.emit(_calling(command))
        await ctx.aclose()
        assert isinstance(result, ToolCalling)
        return result

    return asyncio.run(run())


@pytest.mark.asyncio
async def test_setup_rewrites_only_shell_calls_until_closed(tmp_path):
    ctx = FakeExtensionContext("shell_restore", workspace=tmp_path)
    await setup(ctx)
    rewritten = await ctx.emit(_calling("rm notes.txt"))
    assert isinstance(rewritten, ToolCalling)
    assert shlex.split(str(rewritten.arguments["command"]))[0] == "mv"
    other = _calling("rm notes.txt", tool_name="write_file")
    assert await ctx.emit(other) == other
    await ctx.aclose()
    assert await ctx.emit(_calling("rm notes.txt")) == _calling("rm notes.txt")


def test_shell_rm_hook_rewrites_rm_and_creates_restore_dir(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    os.environ["AKASIC_RESTORE_DIR"] = str(restore_dir)
    try:
        result = _run_shell(_make_plugin_root(tmp_path), "rm -rf foo bar")

        assert restore_dir.is_dir()
        assert shlex.split(str(result.arguments["command"])) == [
            "mv",
            "--",
            "foo",
            "bar",
            str(restore_dir),
        ]
    finally:
        os.environ.pop("AKASIC_RESTORE_DIR", None)


def test_shell_rm_hook_rewrites_sudo_rm(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    os.environ["AKASIC_RESTORE_DIR"] = str(restore_dir)
    try:
        result = _run_shell(_make_plugin_root(tmp_path), "sudo rm -f /tmp/a")

        assert shlex.split(str(result.arguments["command"])) == [
            "sudo",
            "mv",
            "--",
            "/tmp/a",
            str(restore_dir),
        ]
    finally:
        os.environ.pop("AKASIC_RESTORE_DIR", None)


def test_shell_rm_hook_skips_non_rm_command(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    os.environ["AKASIC_RESTORE_DIR"] = str(restore_dir)
    try:
        result = _run_shell(_make_plugin_root(tmp_path), "ls -la")

        assert not restore_dir.exists()
        assert result.arguments["command"] == "ls -la"
    finally:
        os.environ.pop("AKASIC_RESTORE_DIR", None)


def test_default_recovery_is_workspace_isolated_and_leaves_legacy_home_untouched(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("AKASIC_RESTORE_DIR", raising=False)
    legacy = tmp_path / "home/restore"
    legacy.mkdir(parents=True)
    (legacy / "original.txt").write_text("user original", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: legacy.parent)
    for name in ("first", "second"):
        project = tmp_path / name
        project.mkdir()
        result = _run_shell(_make_plugin_root(project), "rm document.txt")
        target = project / "workspace/recovery/shell_restore"
        command = str(result.arguments["command"])
        assert shlex.split(command)[-1] == str(target.resolve())
        assert target.is_dir()
        assert not (project / "workspace/plugin-data/shell_restore").exists()
    assert list(legacy.iterdir()) == [legacy / "original.txt"]
    assert (legacy / "original.txt").read_text(encoding="utf-8") == "user original"


def test_relative_workspace_default_is_absolute_but_explicit_override_is_unchanged(
    tmp_path, monkeypatch
):
    from plugins.shell_restore.backend.plugin import _restore_dir

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AKASIC_RESTORE_DIR", raising=False)
    assert _restore_dir(Path("workspace")) == str(
        tmp_path / "workspace/recovery/shell_restore"
    )
    monkeypatch.setenv("AKASIC_RESTORE_DIR", "custom/restore")
    assert _restore_dir(Path("workspace")) == "custom/restore"
    monkeypatch.setenv("AKASIC_RESTORE_DIR", " ")
    with pytest.raises(ValueError, match="AKASIC_RESTORE_DIR"):
        _restore_dir(tmp_path)
