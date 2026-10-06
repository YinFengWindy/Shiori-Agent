"""Opt-in RPC wiring for a plugin-owned managed installation controller."""

from pathlib import Path

from shiori_sdk.files.staging import staged_import_file
from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .controller import ManagedRuntime


def register_runtime_rpc(
    ctx: ServicePluginContext,
    runtime: ManagedRuntime,
    *,
    namespace: str,
    import_suffix: str | tuple[str, ...],
    import_asset: str | None = None,
    max_bytes: int = 16 * 1024**3,
) -> None:
    """Keep long work behind polling and validate every native import at admission."""

    async def status(_params: dict[str, object]):
        return runtime.status()

    async def prepare(params: dict[str, object]):
        source = None
        if params.get("source"):
            suffix = Path(str(params["source"])).suffix.lower()
            if suffix not in (
                (import_suffix,) if isinstance(import_suffix, str) else import_suffix
            ):
                raise ValueError("环境包格式不受支持")
            source = staged_import_file(
                ctx.workspace,
                namespace,
                str(params["source"]),
                suffix=suffix,
                max_bytes=max_bytes,
            )
        return runtime.submit("prepare", source, import_asset)

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

    ctx.rpc.register("runtime.status", status, concurrency=Concurrency.READ_ONLY)
    for name, handler in [
        ("prepare", prepare),
        ("start", start),
        ("stop", stop),
        ("cancel", cancel),
    ]:
        ctx.rpc.register(
            "runtime." + name, handler, concurrency=Concurrency.INTEGRATION
        )
    ctx.effect("managed_runtime", runtime.close)
    ctx.runtime.on_drain(runtime.close)
