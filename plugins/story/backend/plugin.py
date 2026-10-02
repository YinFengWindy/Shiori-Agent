"""Story mode depends explicitly on the NovelAI plugin within one runtime generation."""

from functools import partial
from typing import Any
from uuid import uuid4

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.plugin_services import ServicePluginContext as PluginRuntimeContext
from plugins.novelai.backend.api import ImageGenerationAPI
from .errors import StorySimulationError
from .rpc import StorySimulationHandler


async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers Story RPC, storage, background work and its required NovelAI API."""
    from shiori_sdk.rpc import Concurrency

    if ctx.workspace is None:
        raise RuntimeError("story requires a workspace")
    novelai = ctx.dependencies.require("novelai")
    if not isinstance(novelai, ImageGenerationAPI):
        raise TypeError("NovelAI dependency must export ImageGenerationAPI")
    handler = StorySimulationHandler(
        workspace=ctx.workspace,
        role_store=ctx.roles,
        storage=ctx.storage,
        background=ctx.background,
        models=ctx.models,
        image_tool=novelai,
    )
    # Only an already-active predecessor can own persisted in-flight turns.
    # First enabling Story after startup must still recover interrupted work.
    if ctx.runtime.was_active:
        handler.skip_startup_recovery()
    ctx.effect("story.close", handler.aclose)
    ctx.runtime.on_drain(handler.drain)

    async def emit(event: dict[str, Any]) -> None:
        await ctx.rpc.emit(
            str(event["method"]).removeprefix("stories."), event["payload"]
        )

    async def invoke(method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return await handler.handle(
                f"stories.{method}",
                payload,
                request_id=str(payload.get("operation_id") or uuid4().hex),
                emit_event=emit,
            )
        except StorySimulationError as exc:
            raise PluginRpcError(exc.code, str(exc)) from exc

    read_methods = {"list", "get", "cg.list"}
    for method in (
        "list",
        "get",
        "cg.list",
        "create",
        "input",
        "continue",
        "cg.retry",
        "cg.regenerate",
    ):
        ctx.rpc.register(
            method,
            partial(invoke, method),
            concurrency=(
                Concurrency.READ_ONLY
                if method in read_methods
                else Concurrency.INTEGRATION
            ),
        )
