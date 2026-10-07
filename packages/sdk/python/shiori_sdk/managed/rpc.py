"""Opt-in RPC wiring for a plugin-owned managed installation controller."""

import os
import re
import stat
from pathlib import Path

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .acquisition import is_bundle
from .controller import ManagedRuntime


def _linked(path: Path) -> bool:
    """Whether the path or any parent is a symbolic link or a junction."""
    return any(
        item.is_symlink() or item.is_junction() for item in (path, *path.parents)
    )


def _local_directory(value: object) -> Path:
    """An existing directory on a drive letter: no UNC or device-namespace path.

    Network shares and device namespaces are not install targets: a share can
    vanish while a service runs from it, and device paths bypass the normal
    path rules the environment's third-party tools rely on.
    """
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("安装位置必须为绝对路径")
    if os.name == "nt" and (
        value.startswith(("\\\\", "//"))
        or not re.fullmatch(r"[A-Za-z]:", Path(value).drive)
    ):
        raise ValueError("安装位置必须位于本机磁盘")
    path = Path(value)
    if not path.is_dir():
        raise ValueError("安装位置不存在")
    return path


def original_import(
    runtime: ManagedRuntime, value: object, suffixes: tuple[str, ...]
) -> Path:
    """Admit a user-selected original by path (``host.pickFilePaths``).

    The file stays where the user keeps it and is never copied or deleted. It
    must be an absolute path to a regular file reached without any link or
    junction (so the verified file is the one the build reads), with an
    accepted suffix; a single-artifact import must also have that artifact's
    exact size. Its SHA-256 is verified while preparation reads it, before any
    extraction.
    """
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("环境包路径必须为绝对路径")
    path = Path(value)
    if path.suffix.lower() not in suffixes:
        raise ValueError("环境包格式不受支持")
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("环境包不存在") from error
    if not stat.S_ISREG(info.st_mode) or _linked(path):
        raise ValueError("环境包必须是普通文件，且路径中不含链接")
    if not is_bundle(path):
        sizes = {item.name: item.size for item in runtime.installation.artifacts}
        if runtime.import_asset not in sizes:
            raise ValueError("环境包格式不受支持")
        if info.st_size != sizes[runtime.import_asset]:
            raise ValueError("环境包大小与固定版本不一致")
    return path


def register_runtime_rpc(
    ctx: ServicePluginContext,
    runtime: ManagedRuntime,
    *,
    namespace: str,
    import_suffix: str | tuple[str, ...],
) -> None:
    """Keep long work behind polling; validate every import and location at admission.

    ``namespace`` names the dedicated directory created inside a location the
    user chooses, so plugins sharing a location never share entries. A
    ``runtime.relocate`` without ``directory`` restores the default location.
    """
    if Path(namespace).name != namespace or namespace in {"", ".", ".."}:
        raise ValueError("无效的环境命名空间")
    suffixes = (import_suffix,) if isinstance(import_suffix, str) else import_suffix

    async def status(_params: dict[str, object]):
        return runtime.status()

    async def prepare(params: dict[str, object]):
        source = None
        if params.get("source"):
            source = original_import(runtime, params["source"], suffixes)
        return runtime.submit("prepare", source)

    async def relocate(params: dict[str, object]):
        if params.get("directory") is None:
            return runtime.relocate(None)
        chosen = _local_directory(params["directory"])
        # Choosing the dedicated directory itself does not nest another one.
        same = os.path.normcase(chosen.name) == os.path.normcase(namespace)
        return runtime.relocate(chosen if same else chosen / namespace)

    async def start(_params: dict[str, object]):
        if runtime.mode() != "managed":
            raise ValueError("请先保存托管连接模式")
        return runtime.submit("start")

    async def stop(_params: dict[str, object]):
        await runtime.stop()
        return runtime.status()

    async def cancel(_params: dict[str, object]):
        await runtime.cancel()
        return runtime.status()

    async def remove(_params: dict[str, object]):
        return runtime.remove()

    ctx.rpc.register("runtime.status", status, concurrency=Concurrency.READ_ONLY)
    for name, handler in [
        ("prepare", prepare),
        ("relocate", relocate),
        ("start", start),
        ("stop", stop),
        ("cancel", cancel),
        ("remove", remove),
    ]:
        ctx.rpc.register(
            "runtime." + name, handler, concurrency=Concurrency.INTEGRATION
        )
    ctx.effect("managed_runtime", runtime.close)
    ctx.runtime.on_drain(runtime.close)
