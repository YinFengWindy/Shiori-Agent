"""Thin OS queries used to reclaim ports held by orphaned managed NapCat trees."""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import psutil

_T = TypeVar("_T")


@dataclass(frozen=True)
class ProcessInfo:
    """Identity of one live process.

    Fields the OS refuses to reveal are None; callers must treat such a process
    as foreign and never kill it.
    """

    pid: int
    name: str | None
    exe: Path | None
    parent_pid: int | None
    create_time: float | None


def port_bindable(port: int) -> bool:
    """Whether a loopback TCP listener could bind this port right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def listener_pid(port: int) -> int | None:
    """Returns the PID listening on a local TCP port, or None when nobody is."""
    for connection in psutil.net_connections(kind="tcp"):
        if (
            connection.status == psutil.CONN_LISTEN
            and connection.laddr
            and connection.laddr.port == port
            and connection.pid
        ):
            return connection.pid
    return None


def _unless_denied(read: Callable[[], _T]) -> _T | None:
    try:
        return read()
    except psutil.AccessDenied:
        return None


def process_info(pid: int) -> ProcessInfo | None:
    """Describes a live process, or returns None once it has already exited."""
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            exe = _unless_denied(process.exe)
            return ProcessInfo(
                pid,
                _unless_denied(process.name),
                Path(exe) if exe else None,
                _unless_denied(process.ppid),
                _unless_denied(process.create_time),
            )
    except psutil.NoSuchProcess:
        return None


def kill_process_tree(info: ProcessInfo, timeout: float = 5) -> None:
    """Force-kills an inspected process and its descendants.

    The creation time recorded in ``info`` pins identity: if the PID has since
    exited and been reused, or the creation time was never readable, nothing
    is killed.
    """
    try:
        root = psutil.Process(info.pid)
        if info.create_time is None or root.create_time() != info.create_time:
            return
        # psutil skips children created before the parent, so reused child
        # PIDs are excluded as well.
        tree = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return
    for process in tree:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(tree, timeout=timeout)
    if alive:
        raise RuntimeError(
            "托管 NapCat 残留进程未能结束："
            + ", ".join(str(process.pid) for process in alive)
        )
