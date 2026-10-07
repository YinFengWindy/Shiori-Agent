"""A plugin-owned child tree, always released through the injected native owner."""

import asyncio
import codecs
import locale
import os
import re
from collections import deque
from pathlib import Path
from typing import TextIO

from shiori_sdk.processes import ProcessOwner, Processes
from .paths import environment_path, native_path

_CHUNK = 64 * 1024
# A child that never ends a line is flushed in bounded pieces of decoded text.
_LINE_LIMIT = 64 * 1024
# A bare carriage return (progress redraw) also ends a line.
_LINE_BREAK = re.compile("\r\n|\r|\n")
_TAIL_LINES = 8
_JOIN_TIMEOUT = 5.0


def private_environment(
    root: Path,
    executables: Path,
    *,
    cache_variables: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Isolate Python/temp files and provider-selected cache variables from the host."""
    root, executables = native_path(root), native_path(executables)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA"))
    }
    temporary = root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env.update(
        PATH=environment_path(executables) + os.pathsep + env.get("PATH", ""),
        PYTHONNOUSERSITE="1",
        TEMP=environment_path(temporary),
        TMP=environment_path(temporary),
    )
    # Third-party archive libraries may append POSIX member names. Extended
    # namespaces disable Win32 slash normalization and would turn that into Win123.
    env.update(
        {
            name: environment_path(root / "cache" / name.lower())
            for name in cache_variables
        }
    )
    env.update(overrides or {})
    return env


def _system_encoding() -> str:
    """The ANSI code page on Windows, even when this interpreter runs in UTF-8 mode."""
    return "mbcs" if os.name == "nt" else locale.getpreferredencoding(False)


class OutputDecoder:
    """Incrementally decode one child's output: UTF-8, else the system code page.

    Python children run with ``-X utf8`` and uv always writes UTF-8, while native
    tools such as 7-Zip write the system code page (GBK on Chinese Windows). A
    child switches to the code page at its first invalid UTF-8 byte. Both
    decoders are incremental, so a character split across reads stays intact.
    """

    def __init__(self):
        self.utf8 = codecs.getincrementaldecoder("utf-8")()
        self.fallback: codecs.IncrementalDecoder | None = None

    def decode(self, data: bytes, final: bool = False) -> str:
        """Return the text completed by ``data``; ``final`` flushes partial bytes."""
        if self.fallback is None:
            buffered, _flag = self.utf8.getstate()
            try:
                return self.utf8.decode(data, final)
            except UnicodeDecodeError:
                self.fallback = codecs.getincrementaldecoder(_system_encoding())(
                    errors="replace"
                )
                data = buffered + data
        return self.fallback.decode(data, final)


def failure_message(summary: str, reason: str, log: Path) -> str:
    """One failure line: what failed, the child's last meaningful output, the log."""
    location = environment_path(log)
    if reason:
        return f"{summary}：{reason}。详见 {location}"
    return f"{summary}，详见 {location}"


class OwnedChild:
    """No PID adoption: only the native owner returned for this spawn may be closed."""

    def __init__(self, processes: Processes):
        self.processes = processes
        self.process: asyncio.subprocess.Process | None = None
        self.owner: ProcessOwner | None = None
        self.log: TextIO | None = None
        self.pump: asyncio.Task[None] | None = None
        self.tail: deque[str] = deque(maxlen=_TAIL_LINES)

    async def start(
        self, command: list[str], *, cwd: Path, env: dict[str, str], log: Path
    ) -> None:
        """Launch a hidden tree whose output is decoded into a private UTF-8 log."""
        if self.process is not None:
            raise RuntimeError("进程已启动")
        # Preserve the caller's executable/cwd spelling. Third-party Python code
        # may require normal sys.prefix semantics for relative DLL/script paths.
        log = native_path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        self.log = log.open("a", encoding="utf-8", newline="")
        self.tail.clear()
        try:
            self.process, self.owner = await self.processes.spawn(
                *command,
                env=env,
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except BaseException:
            self.log.close()
            self.log = None
            raise
        if self.process.stdout is not None:
            self.pump = asyncio.create_task(self._pump(self.process.stdout, self.log))

    async def _pump(self, stream: asyncio.StreamReader, log: TextIO) -> None:
        """Drain the pipe until EOF; a failing log write must never block the child."""
        writable, pending, decoder = True, "", OutputDecoder()

        def emit(lines: list[str]) -> None:
            nonlocal writable
            self.tail.extend(item.strip() for item in lines if item.strip())
            if not writable:
                return
            try:
                log.write("".join(item + "\n" for item in lines))
                log.flush()
            except OSError:
                # A full disk also fails the log. Keep draining so the child can
                # exit; its failure is still reported from the retained tail.
                writable = False

        while chunk := await stream.read(_CHUNK):
            text = pending + decoder.decode(chunk)
            # A trailing CR may be the first half of CRLF; decide on the next read.
            held = "\r" if text.endswith("\r") else ""
            *lines, pending = _LINE_BREAK.split(text[: len(text) - len(held)])
            pending += held
            if len(pending) >= _LINE_LIMIT:
                lines.append(pending)
                pending = ""
            emit(lines)
        pending += decoder.decode(b"", final=True)
        if pending.rstrip("\r"):
            emit([pending.rstrip("\r")])

    async def exit_reason(self) -> str:
        """After the child exited, wait briefly for its last output and name it."""
        if self.pump is not None:
            await asyncio.wait({self.pump}, timeout=_JOIN_TIMEOUT)
        return self.failure_reason()

    def failure_reason(self) -> str:
        """The last meaningful output line, joined with a preceding ``...:`` header."""
        lines = list(self.tail)
        if not lines:
            return ""
        reason = lines[-1]
        if len(lines) > 1 and lines[-2].endswith(":"):
            reason = f"{lines[-2]} {reason}"
        return reason[:200].rstrip("。.")

    async def close(self) -> None:
        """Kill the owned tree and join the child before releasing file handles."""
        process, owner = self.process, self.owner
        if owner is not None:
            owner.close()
        elif process is not None and process.returncode is None:
            process.kill()
        if process is not None:
            await process.wait()
        # Preserve handles on close/wait failure: another owner must not replace
        # a tree whose termination has not actually been observed.
        self.process = self.owner = None
        pump, self.pump = self.pump, None
        try:
            if pump is not None:
                # The owned tree is gone, so EOF follows at once. An unowned
                # descendant (no native owner) could keep the pipe open; never hang.
                _done, waiting = await asyncio.wait({pump}, timeout=_JOIN_TIMEOUT)
                if waiting:
                    pump.cancel()
                    await asyncio.gather(pump, return_exceptions=True)
                else:
                    pump.result()
        finally:
            if self.log is not None:
                self.log.close()
                self.log = None


async def run_owned(
    processes: Processes,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
) -> None:
    """Run one preparation command; cancellation kills and joins its complete tree.

    A non-zero exit raises with the last meaningful output line, e.g. the system
    message of a full disk, and the UTF-8 log location.
    """
    child = OwnedChild(processes)
    try:
        await child.start(command, cwd=cwd, env=env, log=log)
        assert child.process is not None
        code = await child.process.wait()
    finally:
        await child.close()
    if code:
        raise RuntimeError(
            failure_message(f"环境准备命令失败（{code}）", child.failure_reason(), log)
        )
