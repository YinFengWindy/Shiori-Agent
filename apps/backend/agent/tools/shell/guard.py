"""The core's minimal shell guard: commands that wipe a whole disk, home or workspace.

The core runs it on the final ``shell`` command after every ``ToolCalling``
chain (D11), so it holds with shell_safety disabled and after any plugin
rewrote the command. It is deliberately tiny and errs towards letting a
command through: it refuses only three unmistakable catastrophes and never an
ordinary command (``rm file``, ``rm -rf build/``, ``dd of=/dev/null``,
``mkfs.ext4 disk.img``). Interactive-command refusal and the rm→mv rewrite
stay in the shell_safety and shell_restore plugins.

The three rules, checked on every simple command of the line (split at
``;``, ``&&``, ``||``, ``|``, ``&``, parentheses and newlines, after the
``sudo`` / ``env`` / ``VAR=value`` style prefixes, and inside ``sh -c``,
``pwsh -Command`` and ``cmd /c``, at most two wrappers deep):

1. a protected directory — the filesystem root, a drive root, the user's
   home or the workspace root, or everything directly inside one of them
   (``/*``) — removed whole: named by a delete command (``rm``, ``rmdir``,
   PowerShell ``Remove-Item`` and its aliases) or as the source of a move
   (``mv``, ``Move-Item`` and its aliases ``mi`` / ``move``). A move counts
   because it empties the directory just the same, and because a plugin may
   rewrite a delete into a move (shell_restore does) before this check;
2. writing a block device: ``dd of=<device>``, a redirection ``> <device>``,
   or ``mkfs`` / ``mke2fs`` on a device;
3. formatting a drive: PowerShell ``Format-Volume`` / ``Clear-Disk`` and
   ``format <drive>:``.

A command the parser cannot read (unbalanced quotes) passes: the shell
itself rejects most of them, and the guard never blocks on a guess.
"""

from __future__ import annotations

import os
import posixpath
import re
import shlex
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

# Delete commands of POSIX sh and PowerShell (``rm``/``del``/``rd``/``ri``/
# ``erase``/``rmdir`` are aliases of ``Remove-Item`` there).
_DELETE = frozenset({"rm", "rmdir", "remove-item", "ri", "del", "erase", "rd"})
_FORMAT_DRIVE = frozenset({"format-volume", "clear-disk"})
_MOVE = frozenset({"mv", "move-item", "mi", "move"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
_POWERSHELLS = frozenset({"pwsh", "powershell"})
_CMD_SCRIPT_SWITCHES = frozenset({"/c", "/k", "/r"})
# Wrappers that run the next word as the command; their options are skipped.
_PREFIXES = frozenset({"sudo", "doas", "env", "nohup", "time", "exec", "command"})
_PREFIX_OPTIONS_WITH_VALUE = frozenset({"-u", "-g", "-C", "-D", "-R", "-T", "-h"})
_SEPARATORS = frozenset({";", ";;", "&", "&&", "|", "||", "|&", "(", ")"})
_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_BLOCK_DEVICE = re.compile(
    r"/dev/(?:(?:sd|hd|vd|xvd)[a-z]+\d*|nvme\d+n\d+(?:p\d+)?"
    r"|mmcblk\d+(?:p\d+)?|r?disk\d+(?:s\d+)?)"
)
_DRIVE = re.compile(r"[a-z]:")
# Spellings of the home directory a command can name before the shell expands it.
_HOME_WORDS = frozenset(
    {"~", "$home", "${home}", "$env:userprofile", "${env:userprofile}", "$env:home"}
)
_MAX_NESTING = 2


def destructive_command_reason(
    command: str, *, protected_dirs: Iterable[Path] = ()
) -> str | None:
    """Why the core refuses ``command``, or None when it may run.

    ``protected_dirs`` are absolute directories (the workspace root) a delete
    command may not name, besides the root, drive roots and the user's home.
    """
    roots = {_normalized(str(path)) for path in (Path.home(), *protected_dirs)}
    return _line_reason(command, roots, nesting=0)


def _line_reason(command: str, roots: set[str], *, nesting: int) -> str | None:
    tokens = _tokens(command)
    if tokens is None:
        return None
    for index, token in enumerate(tokens[:-1]):
        if token in _REDIRECTS and _BLOCK_DEVICE.fullmatch(tokens[index + 1]):
            return _device_reason(tokens[index + 1])
    for segment in _segments(tokens):
        if (reason := _command_reason(segment, roots, nesting=nesting)) is not None:
            return reason
    return None


def _tokens(command: str) -> list[str] | None:
    # Newlines end a command like ``;``; a backslash-newline only continues it.
    text = re.sub(r"\\\r?\n", " ", command)
    text = re.sub(r"\r?\n", " ; ", text)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    # Backslashes stay literal: PowerShell paths use them as separators.
    lexer.escape = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _segments(tokens: Sequence[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _command_reason(
    segment: Sequence[str], roots: set[str], *, nesting: int
) -> str | None:
    found = _command(segment)
    if found is None:
        return None
    name, arguments = found
    script = _wrapped_script(name, arguments)
    if script is not None:
        if nesting >= _MAX_NESTING:
            return None
        return _line_reason(script, roots, nesting=nesting + 1)
    if name in _DELETE or name in _MOVE:
        targets = _operands(arguments) if name in _DELETE else _move_sources(arguments)
        for target in targets:
            if _names_protected_dir(target, roots):
                return (
                    f"核心安全拦截：{target} 是根目录、用户主目录或工作区根目录，"
                    "不能删除或整个移走。"
                )
        return None
    if name == "dd":
        for argument in arguments:
            device = argument.partition("=")[2]
            if argument.startswith("of=") and _BLOCK_DEVICE.fullmatch(device):
                return _device_reason(device)
        return None
    if name in ("mkfs", "mke2fs") or name.startswith("mkfs."):
        for argument in arguments:
            if _BLOCK_DEVICE.fullmatch(argument):
                return _device_reason(argument)
        return None
    if name in _FORMAT_DRIVE or (
        name == "format"
        and any(_DRIVE.fullmatch(_trimmed(argument)) for argument in arguments)
    ):
        return "核心安全拦截：不能格式化或清空磁盘。"
    return None


def _command(segment: Sequence[str]) -> tuple[str, Sequence[str]] | None:
    """The command name and its arguments, past wrappers and assignments."""
    index = 0
    while index < len(segment):
        token = segment[index]
        name = _command_name(token)
        if _ASSIGNMENT.match(token):
            index += 1
        elif name in _PREFIXES:
            index += 1
            while index < len(segment) and segment[index].startswith("-"):
                skip = 2 if segment[index] in _PREFIX_OPTIONS_WITH_VALUE else 1
                index += skip
        else:
            return name, segment[index + 1 :]
    return None


def _command_name(token: str) -> str:
    name = re.split(r"[\\/]", token)[-1].lower()
    return name.removesuffix(".exe")


def _wrapped_script(name: str, arguments: Sequence[str]) -> str | None:
    """The command line a shell wrapper runs, or None when ``name`` runs none."""
    if name in _SHELLS:
        return _sh_script(arguments)
    if name in _POWERSHELLS:
        return _rest_after(arguments, _is_powershell_command_switch)
    if name == "cmd":
        return _rest_after(arguments, lambda arg: arg.lower() in _CMD_SCRIPT_SWITCHES)
    return None


def _sh_script(arguments: Sequence[str]) -> str | None:
    """The script of ``sh -c <script>`` (also ``-lc`` / ``-ec`` and the like)."""
    for index, argument in enumerate(arguments[:-1]):
        if not argument.startswith("-") or argument.startswith("--"):
            return None
        if "c" in argument[1:]:
            return arguments[index + 1]
    return None


def _is_powershell_command_switch(argument: str) -> bool:
    """``-Command`` or any unambiguous prefix of it (``-c``, ``-com``)."""
    lowered = argument.lower()
    return len(lowered) >= 2 and "-command".startswith(lowered)


def _rest_after(
    arguments: Sequence[str], is_switch: Callable[[str], bool]
) -> str | None:
    """The words after the switch that starts the wrapped command, rejoined."""
    for index, argument in enumerate(arguments):
        if is_switch(argument):
            rest = arguments[index + 1 :]
            return " ".join(rest) if rest else None
    return None


def _operands(arguments: Sequence[str]) -> list[str]:
    """Paths a delete command names: non-option words, and ``-Path:<value>``."""
    operands: list[str] = []
    for argument in arguments:
        if argument == "--" or argument == "-":
            continue
        if argument.startswith("-"):
            _, colon, value = argument.partition(":")
            if colon and value:
                operands.append(value)
            continue
        operands.append(argument)
    return operands


def _move_sources(arguments: Sequence[str]) -> list[str]:
    """What a move takes away: every operand but the destination.

    The destination is the value of ``-t`` / ``--target-directory=`` (POSIX)
    or ``-Destination`` (PowerShell, any unambiguous prefix); without one it
    is the last operand.
    """
    sources: list[str] = []
    explicit_destination = False
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        lowered = argument.lower()
        name, colon, value = argument.partition(":")
        if argument == "-t" or (
            len(name) > 1 and "-destination".startswith(name.lower())
        ):
            explicit_destination = True
            skip_next = not colon
            continue
        if lowered.startswith("--target-directory"):
            explicit_destination = True
            skip_next = "=" not in argument
            continue
        if argument in ("--", "-"):
            continue
        if argument.startswith("-"):
            if colon and value:
                sources.append(value)
            continue
        sources.append(argument)
    return sources if explicit_destination else sources[:-1]


def _names_protected_dir(target: str, roots: set[str]) -> bool:
    path = _normalized(target)
    if path == "/" or _DRIVE.fullmatch(path) or path in _HOME_WORDS:
        return True
    return path in roots


def _normalized(path: str) -> str:
    """``path`` with ``/`` separators, no trailing ``/``, ``/*`` or ``/.``.

    Case-folded on Windows, whose paths ignore case; a POSIX absolute path is
    also resolved lexically (``/tmp/..`` is ``/``).
    """
    text = path.strip().replace("\\", "/")
    while True:
        if text.endswith(("/*", "/.")):
            text = text[:-2] or "/"
        elif len(text) > 1 and text.endswith("/"):
            text = text[:-1]
        else:
            break
    if text.startswith("/"):
        text = "/" if not text.strip("/") else posixpath.normpath(text)
    lowered = text.lower()
    if lowered in _HOME_WORDS or _DRIVE.fullmatch(lowered) or os.name == "nt":
        return lowered
    return text


def _trimmed(argument: str) -> str:
    return argument.lower().rstrip("\\/")


def _device_reason(device: str) -> str:
    return f"核心安全拦截：不能直接写入块设备 {device}。"
