from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from shiori_sdk.tool_hooks import PreToolCtx
from shiori_sdk.tool_hooks import HookOutcome

if TYPE_CHECKING:
    from shiori_sdk.extensions import HookPluginContext as PluginRuntimeContext

INTERACTIVE_COMMANDS = {
    "vi",
    "vim",
    "nvim",
    "nano",
    "sudoedit",
    "visudo",
}

PACKAGE_MANAGERS = {"pacman", "yay", "paru"}
PACKAGE_WRITE_OPTIONS = {
    "--sync",
    "--remove",
    "--upgrade",
    "--sysupgrade",
}


class _ShellSafetyGuard:
    """阻止 shell 工具执行容易卡住的交互式命令；v2 插件不再继承旧 Plugin ABC。"""

    async def block_interactive_shell(self, event: PreToolCtx) -> HookOutcome | None:
        command = str(event.arguments.get("command") or "").strip()
        if not command:
            return None
        reason = self._deny_reason(command)
        if not reason:
            return None
        return HookOutcome(decision="deny", reason=reason)

    def _deny_reason(self, command: str) -> str:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return ""
        if not tokens:
            return ""
        editor = self._find_interactive_command(tokens)
        if editor:
            return f"shell_safety 拦截：{editor} 会打开交互式界面，请改用非交互命令。"
        if self._sudo_needs_password(tokens):
            return "shell_safety 拦截：sudo 可能等待密码，请改用 sudo -n，让它在没有缓存时立即失败。"
        package_manager = self._find_interactive_package_command(tokens)
        if package_manager:
            return f"shell_safety 拦截：{package_manager} 写操作需要加 --noconfirm，避免卡在确认提示。"
        if self._opens_system_editor(tokens):
            return (
                "shell_safety 拦截：该命令会打开系统编辑器，请改用写文件或非交互参数。"
            )
        return ""

    def _find_interactive_command(self, tokens: list[str]) -> str:
        for token in tokens:
            name = Path(token).name
            if name in INTERACTIVE_COMMANDS:
                return name
        return ""

    def _sudo_needs_password(self, tokens: list[str]) -> bool:
        for index, token in enumerate(tokens):
            if Path(token).name != "sudo":
                continue
            if not self._sudo_has_non_interactive_option(tokens[index + 1 :]):
                return True
        return False

    def _sudo_has_non_interactive_option(self, tokens: list[str]) -> bool:
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "--":
                return False
            if not token.startswith("-") or token == "-":
                return False
            if token == "-n" or (
                token.startswith("-")
                and not token.startswith("--")
                and "n" in token[1:]
            ):
                return True
            if token in {"-u", "-g", "-p", "-C", "-D", "-R", "-T", "-h"}:
                index += 2
                continue
            index += 1
        return False

    def _find_interactive_package_command(self, tokens: list[str]) -> str:
        for index, token in enumerate(tokens):
            name = Path(token).name
            if name not in PACKAGE_MANAGERS:
                continue
            args = tokens[index + 1 :]
            if self._has_package_write_option(args) and "--noconfirm" not in args:
                return name
        return ""

    def _has_package_write_option(self, args: list[str]) -> bool:
        for arg in args:
            if arg in PACKAGE_WRITE_OPTIONS:
                return True
            if arg.startswith("-S") or arg.startswith("-R") or arg.startswith("-U"):
                return True
        return False

    def _opens_system_editor(self, tokens: list[str]) -> bool:
        for index, token in enumerate(tokens[:-1]):
            name = Path(token).name
            if name == "systemctl" and tokens[index + 1] == "edit":
                return True
            if name == "crontab" and tokens[index + 1] == "-e":
                return True
        return False


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 shell_safety：注册 shell 工具的 pre-tool hook。

    hook 名由 ToolHooksCapability 统一生成（plugin:{plugin_id}:{handler.__name__}），
    插件不再直接引用宿主的 PluginToolHook 或自行拼接 hook 名（#182 评审）。
    """
    guard = _ShellSafetyGuard()
    ctx.tool_hooks.add_handler(guard.block_interactive_shell, tool_name_filter="shell")
