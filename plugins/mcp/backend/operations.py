"""Connection operations; registry remains the sole state and admission owner."""

from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4
from shiori_sdk.mcp import McpSession, McpToolInfo
from .models import McpConfigError

if TYPE_CHECKING:
    from .registry import McpServerRegistry, ServerState


def start_operation(
    registry: "McpServerRegistry", server: str, kind: str
) -> dict[str, object]:
    """Return immediately; cancellation and connections never occupy RPC lanes."""
    registry._ready()
    state = registry._states[server]
    if kind not in {"disable", "delete"}:
        registry._config(server)
    if kind == "connect" and not registry.store.servers[server].enabled:
        raise McpConfigError("请先启用服务器")
    previous = registry._operations.get(server)
    if kind == "test" and previous and not previous.done():
        raise McpConfigError("服务器操作仍在进行")
    if previous and state.operation and state.operation["kind"] in {"connect", "test"}:
        if not previous.cancelling():
            previous.cancel()
    epoch = state.epoch if kind == "test" else registry._invalidate(server)
    op = {"id": uuid4().hex, "kind": kind, "status": "running", "error": None}
    state.operation = op
    if kind != "test":
        state.status = "connecting" if kind == "connect" else "disabling"
    state.error = None

    async def run():
        try:
            if previous:
                await asyncio.gather(previous, return_exceptions=True)
            if kind == "test":
                await test_connection(registry, server)
            else:
                await close_session(registry, state)
                if kind == "connect":
                    await connect(registry, server, epoch)
                elif state.epoch == epoch:
                    state.status = "disconnected" if kind == "cancel" else "disabled"
            op["status"] = "succeeded"
        except asyncio.CancelledError:
            op["status"] = "cancelled"
            if state.epoch == epoch and kind != "test":
                state.status = "disconnected"
            raise
        except Exception as error:
            op["status"], op["error"] = "failed", registry._safe_error(error)
            if state.epoch == epoch and kind != "test":
                state.status, state.error = "error", op["error"]
        finally:
            registry._changed()

    registry._operations[server] = asyncio.create_task(
        run(), name=f"mcp:{server}:{kind}"
    )
    registry._changed()
    return registry.snapshot()


def cancel_operation(registry: "McpServerRegistry", server: str) -> dict[str, object]:
    """Cancel one operation without deleting its saved settings."""
    registry._config(server)
    task = registry._operations.get(server)
    state = registry._states[server]
    if task and not task.done() and state.operation:
        if state.operation["kind"] == "connect":
            return start_operation(registry, server, "cancel")
        if state.operation["kind"] == "test":
            state.operation["status"] = "cancelled"
            if not task.cancelling():
                task.cancel()
            registry._changed()
    return registry.snapshot()


async def wait_operations(registry: "McpServerRegistry") -> None:
    """Wait for current finite operations, used by compatibility tools and tests."""
    await asyncio.gather(*tuple(registry._operations.values()), return_exceptions=True)


async def close_session(registry: "McpServerRegistry", state: ServerState) -> None:
    session, state.session = state.session, None
    if state.calls:
        await asyncio.gather(*tuple(state.calls), return_exceptions=True)
    if session:
        await disconnect(session)


def new_session(registry: "McpServerRegistry", server: str) -> McpSession:
    config = registry.store.servers[server]
    credentials = registry.store.credentials(config)
    return registry._processes.mcp(
        server,
        list(credentials.command),
        dict(credentials.env),
        config.transport.cwd,
        own_process_tree=True,
    )


async def test_connection(registry: "McpServerRegistry", server: str) -> None:
    session = new_session(registry, server)
    try:
        await session.connect()
    finally:
        await disconnect(session)


async def connect(registry: "McpServerRegistry", server: str, epoch: int) -> None:
    state = registry._states[server]
    session = new_session(registry, server)
    adopted = False
    try:
        infos = await session.connect()
        config = registry._config(server)
        if state.epoch != epoch or not config.enabled:
            raise McpConfigError("连接已被更新")
        state.infos = [
            McpToolInfo(
                info.name,
                registry._redact(server, info.description),
                registry._scrub(server, info.input_schema),
            )
            for info in infos
        ]
        state.session, state.status = session, "connected"
        registry._register(server, state)
        adopted = True
    finally:
        if not adopted:
            registry._unregister(state)
            if state.session is session:
                state.session = None
            await disconnect(session)
    registry._changed()


async def disconnect(session: McpSession) -> None:
    """Complete owned cleanup even if another management request cancels twice."""
    cleanup = asyncio.create_task(session.disconnect())
    cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancelled = True
    cleanup.result()
    if cancelled:
        raise asyncio.CancelledError
