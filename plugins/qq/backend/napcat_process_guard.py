"""Thin OS queries used to reclaim ports held by orphaned managed NapCat trees."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class ProcessInfo:
    """Identity of one live process; ``exe`` is None when the OS denies access."""

    pid: int
    name: str
    exe: Path | None
    parent_pid: int
    create_time: float


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


def process_info(pid: int) -> ProcessInfo | None:
    """Describes a live process, or returns None once it has already exited."""
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            name = process.name()
            parent_pid = process.ppid()
            create_time = process.create_time()
            try:
                exe: Path | None = Path(process.exe())
            except psutil.AccessDenied:
                # Elevated or system processes hide their image path; callers
                # must treat such owners as foreign.
                exe = None
    except psutil.NoSuchProcess:
        return None
    return ProcessInfo(pid, name, exe, parent_pid, create_time)


def kill_process_tree(pid: int, timeout: float = 5) -> None:
    """Force-kills a process and every descendant, failing if any survives."""
    try:
        root = psutil.Process(pid)
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
