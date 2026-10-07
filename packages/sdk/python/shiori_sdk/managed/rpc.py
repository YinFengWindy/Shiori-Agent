"""Opt-in RPC wiring for a plugin-owned managed installation controller."""

import stat
from pathlib import Path

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .acquisition import is_bundle
from .controller import ManagedRuntime


def original_import(
    runtime: ManagedRuntime,
    value: object,
    suffixes: tuple[str, ...],
    import_asset: str | None,
) -> Path:
    """Admit a user-selected original by path (``host.pickFilePaths``).

    The file stays where the user keeps it and is never copied or deleted. It
    must be an absolute path to a regular file (not a link) with an accepted
    suffix; a single-artifact import must also have that artifact's exact size.
    Its SHA-256 is verified while preparation reads it, before any extraction.
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
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("环境包必须是普通文件")
    if not is_bundle(path):
        sizes = {item.name: item.size for item in runtime.installation.artifacts}
        if import_asset not in sizes:
            raise ValueError("环境包格式不受支持")
        if info.st_size != sizes[import_asset]:
            raise ValueError("环境包大小与固定版本不一致")
    return path


def register_runtime_rpc(
    ctx: ServicePluginContext,
    runtime: ManagedRuntime,
    *,
    namespace: str,
    import_suffix: str | tuple[str, ...],
    import_asset: str | None = None,
) -> None:
    """Keep long work behind polling; validate every import and location at admission.

    ``namespace`` names the dedicated directory created inside a location the
    user chooses, so plugins sharing a location never share entries.
    """
    if Path(namespace).name != namespace or namespace in {"", ".", ".."}:
        raise ValueError("无效的环境命名空间")
    suffixes = (import_suffix,) if isinstance(import_suffix, str) else import_suffix

    async def status(_params: dict[str, object]):
        return runtime.status()

    async def prepare(params: dict[str, object]):
        source = None
        if params.get("source"):
            source = original_import(runtime, params["source"], suffixes, import_asset)
        return runtime.submit("prepare", source, import_asset)

    async def relocate(params: dict[str, object]):
        directory = params.get("directory")
        if not isinstance(directory, str) or not Path(directory).is_absolute():
            raise ValueError("安装位置必须为绝对路径")
        chosen = Path(directory)
        if not chosen.is_dir():
            raise ValueError("安装位置不存在")
        # Choosing the dedicated directory itself does not nest another one.
        return runtime.relocate(
            chosen if chosen.name == namespace else chosen / namespace
        )

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
