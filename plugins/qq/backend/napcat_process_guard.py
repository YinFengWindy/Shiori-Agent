"""Reclaims ports held by orphaned managed NapCat trees, over thin OS queries."""

from __future__ import annotations

import asyncio
import os
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


async def reclaim_port(port: int, managed_root: Path) -> None:
    """Frees a port held by an orphaned tree from this plugin's NapCat install.

    A crashed bridge can leave NapCat alive on the account's persisted ports;
    switching ports is not an option because the orphan still owns the QQ
    profile. Only processes whose image lives under ``managed_root`` and whose
    launching bridge is gone are killed; any other owner is reported and left
    untouched.
    """
    if port_bindable(port):
        return
    pid = listener_pid(port)
    owner = process_info(pid) if pid is not None else None
    if owner is None or not _is_managed(owner, managed_root):
        detail = ""
        if owner is not None:
            detail = f"（PID {owner.pid} {owner.name or '未知进程'}）"
        elif pid is not None:
            detail = f"（PID {pid}）"
        raise RuntimeError(f"托管 NapCat 端口 {port} 已被占用{detail}")
    # Climb to the index.js launcher so the whole orphaned tree dies with it.
    root = owner
    while True:
        parent = _genuine_parent(root)
        if parent is None or not _is_managed(parent, managed_root):
            break
        root = parent
    # A launcher whose bridge is still alive belongs to a running Shiori
    # (e.g. packaged and dev builds sharing one data dir), not to an orphan.
    if parent is not None:
        holder = "当前 Shiori" if parent.pid == os.getpid() else "另一个运行中的 Shiori"
        raise RuntimeError(
            f"托管 NapCat 端口 {port} 被{holder} 占用（PID {parent.pid}）"
        )
    await asyncio.to_thread(kill_process_tree, root)
    for _ in range(50):
        if port_bindable(port):
            return
        await asyncio.sleep(0.1)
    raise RuntimeError(f"托管 NapCat 端口 {port} 在结束残留进程后仍被占用")


def _is_managed(info: ProcessInfo, managed_root: Path) -> bool:
    """Whether a fully inspectable process runs an image under managed-napcat."""
    return (
        info.exe is not None
        and info.create_time is not None
        and info.parent_pid is not None
        and info.exe.resolve().is_relative_to(managed_root.resolve())
    )


def _genuine_parent(child: ProcessInfo) -> ProcessInfo | None:
    """Returns the live genuine parent; a newer process on a reused PID is not.

    An uninspectable parent counts as genuine so it is never presumed dead.
    """
    if child.parent_pid is None:
        return None
    parent = process_info(child.parent_pid)
    if (
        parent is not None
        and parent.create_time is not None
        and child.create_time is not None
        and parent.create_time > child.create_time
    ):
        return None
    return parent
