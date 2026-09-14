"""Story mode depends explicitly on the NovelAI plugin within one runtime generation."""

from functools import partial
from typing import Any
from uuid import uuid4

from agent.plugin_host.bridge_events import PluginRpcError
from agent.plugin_host.runtime_context import PluginRuntimeContext
from core.roles import RoleStore
from plugins.novelai.backend.tool import GenerateImageTool
from .errors import StorySimulationError
from .rpc import StorySimulationHandler

async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers Story RPC, storage, background work and its required NovelAI API."""
    from desktop_bridge.method_policy import Concurrency

    novelai = ctx.dependencies.require("novelai")
    if not isinstance(novelai, GenerateImageTool):
        raise TypeError("NovelAI 插件未提供兼容的生图接口")
    handler = StorySimulationHandler(
        workspace=ctx.workspace,
        role_store=RoleStore(ctx.workspace),
        role_runtime_registry=ctx.role_runtime_registry,
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
