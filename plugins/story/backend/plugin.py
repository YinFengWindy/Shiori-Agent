"""Story mode depends explicitly on the NovelAI plugin within one runtime generation."""

from functools import partial
from typing import Any
from uuid import uuid4

from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.plugin_services import ServicePluginContext as PluginRuntimeContext
from shiori_sdk.core.services import (
    BACKGROUND,
    DEPENDENCIES,
    MODELS,
    ROLES,
    RPC,
    RUNTIME,
    WORKSPACE,
)
from plugins.novelai.backend.api import ImageGenerationAPI
from .errors import StorySimulationError
from .rpc import StorySimulationHandler


async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers Story RPC, storage, background work and its required NovelAI API."""
    from shiori_sdk.rpc import Concurrency

    novelai = ctx.require(DEPENDENCIES).require("novelai")
    if not isinstance(novelai, ImageGenerationAPI):
        raise TypeError("NovelAI dependency must export ImageGenerationAPI")
    handler = StorySimulationHandler(
        workspace=ctx.require(WORKSPACE),
        role_store=ctx.require(ROLES),
        background=ctx.require(BACKGROUND),
        models=ctx.require(MODELS),
        image_tool=novelai,
    )
    # Only an already-active predecessor can own persisted in-flight turns.
    # First enabling Story after startup must still recover interrupted work.
    if ctx.require(RUNTIME).was_active:
        handler.skip_startup_recovery()
    ctx.effect("story.close", handler.aclose)
    ctx.require(RUNTIME).on_drain(handler.drain)

    async def emit(event: dict[str, Any]) -> None:
        await ctx.require(RPC).emit(
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
        ctx.require(RPC).register(
            method,
            partial(invoke, method),
            concurrency=(
                Concurrency.READ_ONLY
                if method in read_methods
                else Concurrency.INTEGRATION
            ),
        )
