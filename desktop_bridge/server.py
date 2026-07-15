from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any, cast

from bootstrap.tools import CoreRuntime
from core.integrations.novelai.store import NovelAIStore
from core.roles import RoleStore
from desktop_bridge.models import BridgeError, BridgeResponse
from desktop_bridge.request_dispatcher import BridgeRequestDispatcher
from desktop_bridge.service import DesktopBridgeService
from desktop_bridge.stream_writer import BridgeStreamWriter

logger = logging.getLogger("desktop.bridge")

ReadLine = Callable[[], Awaitable[str | None]]
WritePayload = Callable[[dict[str, Any]], Awaitable[None]]


class DesktopBridgeServer:
    """Serves the desktop JSON-lines bridge for one application runtime."""

    def __init__(self, runtime: CoreRuntime) -> None:
        self.runtime = runtime
        self.role_store = RoleStore(runtime.session_manager.workspace)
        spawn_tool = runtime.tools.get_tool("spawn") if getattr(runtime, "tools", None) else None
        self.service = DesktopBridgeService(
            workspace=runtime.session_manager.workspace,
            role_store=self.role_store,
            session_manager=runtime.session_manager,
            agent_loop=runtime.loop,
            event_bus=runtime.event_bus,
            config=getattr(runtime, "config", None),
            novelai_store=NovelAIStore(runtime.session_manager.workspace),
            push_tool=getattr(runtime, "push_tool", None),
            relationship_runtime=getattr(runtime, "relationship_runtime", None),
            presence=getattr(runtime, "presence", None),
            scheduler=getattr(runtime, "scheduler", None),
            subagent_manager=getattr(spawn_tool, "manager", None),
            memory_optimizer=getattr(runtime, "memory_optimizer", None),
        )

    async def serve_streams(
        self,
        *,
        read_line: ReadLine,
        write_payload: WritePayload,
    ) -> None:
        """Dispatches stream requests concurrently and serializes all output frames."""

        writer = BridgeStreamWriter(write_payload)
        dispatcher = BridgeRequestDispatcher()

        async def _emit_event(payload: dict[str, Any]) -> None:
            await writer.write(payload)

        async def _handle_request(request: dict[str, Any]) -> None:
            try:
                response = await self.service.handle(
                    request,
                    emit_event=_emit_event,
                )
            except Exception as exc:
                request_id = str(request.get("id") or "").strip() or "bridge-request"
                method = str(request.get("method") or "").strip() or "bridge.internal"
                logger.exception("desktop bridge request failed: %s", method)
                response = BridgeResponse(
                    id=request_id,
                    type="response",
                    method=method,
                    error=BridgeError(code="internal_error", message=str(exc)),
                )
            await writer.write(response.to_dict())

        self.service.add_event_listener(_emit_event)

        try:
            while True:
                raw = await read_line()
                if raw is None:
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    request = json.loads(raw)
                except json.JSONDecodeError as exc:
                    response = BridgeResponse(
                        id="bridge-request",
                        type="response",
                        method="invalid_request",
                        error=BridgeError(
                            code="invalid_request",
                            message=f"invalid JSON: {exc.msg}",
                        ),
                    )
                else:
                    if not isinstance(request, dict):
                        response = BridgeResponse(
                            id="bridge-request",
                            type="response",
                            method="invalid_request",
                            error=BridgeError(
                                code="invalid_request",
                                message="request 必须是对象",
                            ),
                        )
                    else:
                        request = cast(dict[str, Any], request)
                        dispatcher.submit(
                            request,
                            lambda request=request: _handle_request(request),
                        )
                        await asyncio.sleep(0)
                        continue
                await writer.write(response.to_dict())
        finally:
            self.service.remove_event_listener(_emit_event)
            await dispatcher.aclose(cancel=True)
            await self.service.aclose()
            await writer.aclose()

    async def serve_stdio(self) -> None:
        """Runs the bridge against process stdin and stdout."""

        async def _read_line() -> str | None:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return None
            return line

        async def _write_payload(payload: dict[str, Any]) -> None:
            text = json.dumps(payload, ensure_ascii=False) + "\n"
            _ = await asyncio.to_thread(sys.stdout.write, text)
            _ = await asyncio.to_thread(sys.stdout.flush)

        await self.serve_streams(
            read_line=_read_line,
            write_payload=_write_payload,
        )
