from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any
import pytest

from agent.plugin_host import HostServices, PluginKernel
from agent.tool_hooks import ToolExecutionRequest, ToolExecutor
from bus.event_bus import EventBus
from shiori_plugin_testkit.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[1]


async def _invoke(tool_name: str, arguments: dict[str, Any]) -> Any:
    return {"tool": tool_name, "arguments": dict(arguments)}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "shell_restore")
    return root


def _run_shell(root: Path, command: str) -> Any:
    bus = EventBus()
    kernel = PluginKernel(
        [root],
        services=HostServices(event_bus=bus, workspace=root.parent / "workspace"),
    )
    _run(kernel.load_all())
    return _run(
        ToolExecutor(kernel.tool_hooks).execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="shell",
                arguments={"command": command, "description": "测试命令"},
                source="passive",
            ),
            _invoke,
        )
    )


def test_shell_restore_hook_name_matches_legacy_convention(tmp_path: Path) -> None:
    """hook 名由 ToolHooksCapability 统一生成，须与旧系统
    f"plugin:{instance.name}:{md.handler_name}" 逐字一致（#182 评审）。"""
    bus = EventBus()
    kernel = PluginKernel(
        [_make_plugin_root(tmp_path)],
        services=HostServices(event_bus=bus, workspace=tmp_path / "workspace"),
    )
    _run(kernel.load_all())

    assert [h.name for h in kernel.tool_hooks] == [
        "plugin:shell_restore:rewrite_rm_to_mv"
    ]


def test_shell_rm_hook_rewrites_rm_and_creates_restore_dir(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    os.environ["AKASIC_RESTORE_DIR"] = str(restore_dir)
    try:
        result = _run_shell(_make_plugin_root(tmp_path), "rm -rf foo bar")

        assert result.status == "success"
        assert restore_dir.is_dir()
        assert shlex.split(result.final_arguments["command"]) == [
            "mv",
            "--",
            "foo",
            "bar",
            str(restore_dir),
        ]
        assert shlex.split(result.output["arguments"]["command"]) == [
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

        assert result.status == "success"
        assert shlex.split(result.final_arguments["command"]) == [
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

        assert result.status == "success"
        assert not restore_dir.exists()
        assert result.final_arguments["command"] == "ls -la"
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
        assert shlex.split(result.final_arguments["command"])[-1] == str(
            target.resolve()
        )
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
