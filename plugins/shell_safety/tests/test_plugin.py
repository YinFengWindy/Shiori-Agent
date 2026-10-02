from __future__ import annotations
import asyncio
from pathlib import Path
import pytest
from shiori_sdk.tool_hooks import PreToolCtx
from shiori_sdk.testing.extensions import FakeExtensionContext
from plugins.shell_safety.backend.plugin import setup


def _make_plugin_root(tmp_path: Path) -> Path:
    return tmp_path / "plugins"


def _run_shell(root: Path, command: str):
    async def run():
        ctx = FakeExtensionContext("shell_safety", workspace=root.parent / "workspace")
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
    ctx = FakeExtensionContext("shell_safety", workspace=tmp_path)
    await setup(ctx)
    assert len(ctx.tool_hooks.handlers) == 1
    assert ctx.tool_hooks.handlers[0].tool_name_filter == "shell"
    assert ctx.tool_hooks.handlers[0].handler_name == "block_interactive_shell"
    await ctx.aclose()
    assert ctx.tool_hooks.handlers == []


def test_shell_safety_blocks_sudo_without_non_interactive(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo pacman -Syu --noconfirm")

    assert result.decision == "deny"
    assert "sudo -n" in result.reason


def test_shell_safety_blocks_interactive_editor(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo -n vim /etc/example.service")

    assert result.decision == "deny"
    assert "vim" in result.reason


def test_shell_safety_blocks_package_write_without_noconfirm(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "pacman -Syu")

    assert result.decision == "deny"
    assert "--noconfirm" in result.reason


def test_shell_safety_allows_non_interactive_package_write(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "sudo -n pacman -Syu --noconfirm")

    assert result.decision == "pass"
    assert result.updated_input["command"] == "sudo -n pacman -Syu --noconfirm"


def test_shell_safety_allows_package_query(tmp_path: Path) -> None:
    result = _run_shell(_make_plugin_root(tmp_path), "pacman -Q")

    assert result.decision == "pass"
    assert result.updated_input["command"] == "pacman -Q"
