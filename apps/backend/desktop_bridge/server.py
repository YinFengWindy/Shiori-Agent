from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any, TextIO, cast
from pathlib import Path

from bootstrap.app import AppRuntime
from bootstrap.tools import CoreRuntime
from core.roles import RoleStore
from desktop_bridge.models import BridgeError, BridgeResponse
from desktop_bridge.request_dispatcher import BridgeRequestDispatcher
from desktop_bridge.runtime.factory import build_desktop_service
from desktop_bridge.stream_writer import BridgeStreamWriter

logger = logging.getLogger("desktop.bridge")

ReadLine = Callable[[], Awaitable[str | None]]
WritePayload = Callable[[dict[str, Any]], Awaitable[None]]


class DesktopBridgeServer:
    """Serves the desktop JSON-lines bridge for one application runtime."""

    def __init__(
        self,
        runtime: CoreRuntime,
        *,
        app: AppRuntime | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.runtime = runtime
        registry = runtime.role_runtime_registry
        repository = registry.repository if registry is not None else None
        self.role_store = (
            repository.store
            if repository is not None
            else RoleStore(runtime.session_manager.workspace)
        )
        self._event_bus = runtime.event_bus if app is None else app.event_bus
        if app is not None:
            if config_path is None:
                raise ValueError("config_path required for runtime reload")
            from desktop_bridge.runtime.service import ReloadableDesktopService

            self.service = ReloadableDesktopService(app, config_path, self.role_store)
        else:
            self.service = build_desktop_service(runtime, self.role_store)

    async def serve_streams(
        self,
        *,
        read_line: ReadLine,
        write_payload: WritePayload,
    ) -> None:
        """Dispatches stream requests concurrently and serializes all output frames."""

        self.service.start_background_tasks()
        writer = BridgeStreamWriter(write_payload)
        dispatcher = BridgeRequestDispatcher(
            policy_resolver=self.service.resolve_method_policy
        )

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

    async def serve_stdio(self, *, output: TextIO | None = None) -> None:
        """Run against stdin and a captured protocol stream, defaulting to stdout."""

        protocol_output = sys.stdout if output is None else output
        # The Electron side always sends and decodes UTF-8 JSON lines.  Windows
        # otherwise gives these streams the active console code page (usually
        # CP936), which corrupts Chinese payloads when global UTF-8 is disabled.
        for stream in (sys.stdin, protocol_output, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="strict")

        async def _read_line() -> str | None:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return None
            return line

        async def _write_payload(payload: dict[str, Any]) -> None:
            text = json.dumps(payload, ensure_ascii=False) + "\n"
            _ = await asyncio.to_thread(protocol_output.write, text)
            _ = await asyncio.to_thread(protocol_output.flush)

        await self.serve_streams(
            read_line=_read_line,
            write_payload=_write_payload,
        )
