from __future__ import annotations
import asyncio
import os
import shlex
from pathlib import Path
import pytest
from shiori_sdk.tool_hooks import PreToolCtx
from shiori_sdk.testing.extensions import FakeExtensionContext
from plugins.shell_restore.backend.plugin import setup


def _make_plugin_root(tmp_path: Path) -> Path:
    return tmp_path / "plugins"


def _run_shell(root: Path, command: str):
    async def run():
        ctx = FakeExtensionContext("shell_restore", workspace=root.parent / "workspace")
        await setup(ctx)
        event = PreToolCtx(
            "", "", "", "shell", {"command": command, "description": "测试命令"}
        )
        outcome = await ctx.tool_hooks.dispatch(event)
        if outcome.updated_input is None:
            outcome.updated_input = event.arguments
        await ctx.aclose()
        return outcome

    return asyncio.run(run())


@pytest.mark.asyncio
async def test_setup_registers_the_filtered_handler(tmp_path):
    ctx = FakeExtensionContext("shell_restore", workspace=tmp_path)
    await setup(ctx)
    assert len(ctx.tool_hooks.handlers) == 1
    assert ctx.tool_hooks.handlers[0].tool_name_filter == "shell"
    assert ctx.tool_hooks.handlers[0].handler_name == "rewrite_rm_to_mv"
    await ctx.aclose()
    assert ctx.tool_hooks.handlers == []


def test_shell_rm_hook_rewrites_rm_and_creates_restore_dir(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    os.environ["AKASIC_RESTORE_DIR"] = str(restore_dir)
    try:
        result = _run_shell(_make_plugin_root(tmp_path), "rm -rf foo bar")

        assert result.decision == "pass"
        assert restore_dir.is_dir()
        assert shlex.split(result.updated_input["command"]) == [
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

        assert result.decision == "pass"
        assert shlex.split(result.updated_input["command"]) == [
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

        assert result.decision == "pass"
        assert not restore_dir.exists()
        assert result.updated_input["command"] == "ls -la"
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
        assert shlex.split(result.updated_input["command"])[-1] == str(target.resolve())
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
