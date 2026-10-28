from __future__ import annotations

import logging
import os
import shlex
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from shiori_sdk.core.tools import ToolCalling
from shiori_sdk.core.services import WORKSPACE

if TYPE_CHECKING:
    from shiori_sdk.extensions import HookPluginContext as PluginRuntimeContext

logger = logging.getLogger("plugin.shell_restore")


def _restore_dir(workspace: Path) -> str:
    configured = os.environ.get("AKASIC_RESTORE_DIR")
    if configured is not None:
        if not configured.strip():
            raise ValueError("AKASIC_RESTORE_DIR 不能为空")
        return configured
    return str((workspace / "recovery" / "shell_restore").resolve())


def rewrite_command(command: str, *, restore_dir: str) -> str | None:
    """把 `rm ...` 命令改写为 `mv -- targets... restore_dir`；非 rm 命令返回 None。

    模块级纯函数，供本插件的 ``ToolCalling`` 处理器与测试 fixture 共用同一份改写逻辑。
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    # 读取 rm 前面的前缀（sudo、env、VAR=val 等）
    prefix: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if Path(token).name == "rm":
            break
        if token == "sudo" or token == "env" or "=" in token:
            prefix.append(token)
            i += 1
            continue
        return None
    if i >= len(tokens) or Path(tokens[i]).name != "rm":
        return None
    # 跳过 rm 名字本身
    i += 1
    # 跳过 rm 选项，收集目标路径
    targets: list[str] = []
    parsing_options = True
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if parsing_options and token == "--":
            parsing_options = False
            continue
        if parsing_options and token.startswith("-") and token != "-":
            continue
        parsing_options = False
        targets.append(token)
    if not targets:
        return None
    # 改写为 mv -- targets... restore_dir
    parts = [*prefix, "mv", "--"]
    parts.extend(targets)
    parts.append(restore_dir)
    return shlex.join(parts)


class _RmRewriter:
    """shell 工具调用的 ``ToolCalling`` 处理器：命中 rm 时改写为 mv。"""

    def __init__(self, restore_dir: str) -> None:
        self._restore_dir = restore_dir

    async def rewrite_rm_to_mv(self, event: ToolCalling) -> ToolCalling:
        """命中 rm 时改写为 mv 并确保 restore 目录存在；其余调用原样透传。"""
        if event.tool_name != "shell":
            return event
        command = str(event.arguments.get("command", "")).strip()
        rewritten = rewrite_command(command, restore_dir=self._restore_dir)
        if rewritten is None:
            return event
        Path(self._restore_dir).mkdir(parents=True, exist_ok=True)
        # logger 已按插件命名（"plugin.shell_restore"），日志消息里不再重复插件名
        logger.info("[rewrite_rm_to_mv] rm → mv: %r", rewritten)
        return replace(event, arguments={**event.arguments, "command": rewritten})


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 shell_restore：在 ``ToolCalling`` 上把 shell 工具的 rm 改写为 mv。"""
    rewriter = _RmRewriter(_restore_dir(ctx.require(WORKSPACE)))
    ctx.on(ToolCalling, rewriter.rewrite_rm_to_mv)
