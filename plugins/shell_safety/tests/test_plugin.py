from __future__ import annotations
import asyncio
from pathlib import Path
import pytest
from shiori_sdk.core.tools import ToolCalling, ToolVeto
from shiori_sdk.kernel import Veto
from shiori_sdk.testing.extensions import FakeExtensionContext
from plugins.shell_safety.backend.plugin import setup


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


def _run_shell(root: Path, command: str) -> ToolCalling | Veto:
    async def run():
        ctx = FakeExtensionContext("shell_safety", workspace=root.parent / "workspace")
        await setup(ctx)
        result = await ctx.emit(_calling(command))
        await ctx.aclose()
        return result

    return asyncio.run(run())


@pytest.mark.asyncio
async def test_setup_joins_tool_calling_for_shell_only_until_closed(tmp_path):
    ctx = FakeExtensionContext("shell_safety", workspace=tmp_path)
    await setup(ctx)
    assert isinstance(await ctx.emit(_calling("vim notes.txt")), ToolVeto)
    other = _calling("vim notes.txt", tool_name="write_file")
    assert await ctx.emit(other) == other
    await ctx.aclose()
    assert await ctx.emit(_calling("vim notes.txt")) == _calling("vim notes.txt")


def test_shell_safety_blocks_sudo_without_non_interactive(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo pacman -Syu --noconfirm")

    assert isinstance(result, Veto)
    assert "sudo -n" in result.reason


def test_shell_safety_blocks_interactive_editor(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo -n vim /etc/example.service")

    assert isinstance(result, Veto)
    assert "vim" in result.reason


def test_shell_safety_blocks_package_write_without_noconfirm(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "pacman -Syu")

    assert isinstance(result, Veto)
    assert "--noconfirm" in result.reason


def test_shell_safety_allows_non_interactive_package_write(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo -n pacman -Syu --noconfirm")

    assert isinstance(result, ToolCalling)
    assert result.arguments["command"] == "sudo -n pacman -Syu --noconfirm"


def test_shell_safety_allows_package_query(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "pacman -Q")

    assert isinstance(result, ToolCalling)
    assert result.arguments["command"] == "pacman -Q"
