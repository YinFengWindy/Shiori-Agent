from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from bootstrap.tools import CoreRuntime
from core.integrations.novelai.store import NovelAIStore
from core.roles import RoleStore
from desktop_bridge.models import BridgeError, BridgeResponse
from desktop_bridge.service import DesktopBridgeService

logger = logging.getLogger("desktop.bridge")


class DesktopBridgeServer:
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

    async def serve_streams(self, *, read_line, write_payload) -> None:
        write_lock = asyncio.Lock()

        async def _emit_event(payload: dict[str, Any]) -> None:
            async with write_lock:
                await write_payload(payload)

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
                        try:
                            response = await self.service.handle(
                                request,
                                emit_event=_emit_event,
                            )
                        except Exception as exc:
                            request_id = (
                                str(request.get("id") or "").strip() or "bridge-request"
                            )
                            method = (
                                str(request.get("method") or "").strip()
                                or "bridge.internal"
                            )
                            logger.exception(
                                "desktop bridge request failed: %s", method
                            )
                            response = BridgeResponse(
                                id=request_id,
                                type="response",
                                method=method,
                                error=BridgeError(
                                    code="internal_error",
                                    message=str(exc),
                                ),
                            )
                async with write_lock:
                    await write_payload(response.to_dict())
        finally:
            self.service.remove_event_listener(_emit_event)

    async def serve_stdio(self) -> None:
        async def _read_line() -> str | None:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return None
            return line

        async def _write_payload(payload: dict[str, Any]) -> None:
            text = json.dumps(payload, ensure_ascii=False) + "\n"
            await asyncio.to_thread(sys.stdout.write, text)
            await asyncio.to_thread(sys.stdout.flush)

        await self.serve_streams(
            read_line=_read_line,
            write_payload=_write_payload,
        )
