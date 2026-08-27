from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from .formatting import API_BASE, TOKEN_URL

logger = logging.getLogger(__name__)


@dataclass
class _TokenCache:
    token: str
    expires_at: float


class _GatewayMixin:
    """Owns QQBot access tokens, REST requests, and Gateway reconnects."""

    async def _gateway_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                token = await self._get_access_token()
                gateway = await self._api_request("GET", "/gateway", token=token)
                await self._run_gateway(str(gateway["url"]), token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[qqbot] Gateway 连接失败: %s", exc)
                await asyncio.sleep(5)

    async def _run_gateway(self, url: str, token: str) -> None:
        last_seq: int | None = None
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            async with self._websocket_connect(url) as websocket:
                async for raw in websocket:
                    payload = json.loads(raw)
                    op = payload.get("op")
                    raw_data = payload.get("d")
                    data = (
                        cast(dict[str, Any], raw_data)
                        if isinstance(raw_data, dict)
                        else {}
                    )
                    event_type = str(payload.get("t") or "")
                    if isinstance(payload.get("s"), int):
                        last_seq = int(payload["s"])
                    if op == 10:
                        heartbeat_task = asyncio.create_task(
                            self._heartbeat(
                                websocket,
                                int(data["heartbeat_interval"]),
                                lambda: last_seq,
                            ),
                            name="qqbot_heartbeat",
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    "op": 2,
                                    "d": {
                                        "token": f"QQBot {token}",
                                        "intents": self._intents(),
                                        "shard": [0, 1],
                                    },
                                }
                            )
                        )
                    elif op == 0:
                        await self._handle_dispatch(event_type, data)
                    elif op == 7:
                        break
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _heartbeat(
        self,
        websocket: Any,
        heartbeat_ms: int,
        seq_fn: Callable[[], int | None],
    ) -> None:
        while True:
            await asyncio.sleep(max(1, heartbeat_ms / 1000))
            await websocket.send(json.dumps({"op": 1, "d": seq_fn()}))

    @staticmethod
    def _intents() -> int:
        return 1 << 25

    async def _get_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token.expires_at - 300:
            return self._token.token
        response = await self._client.post(
            TOKEN_URL,
            json={"appId": self._app_id, "clientSecret": self._client_secret},
        )
        response.raise_for_status()
        data = response.json()
        token = str(data["access_token"])
        expires_in = int(data.get("expires_in") or 7200)
        self._token = _TokenCache(token=token, expires_at=now + expires_in)
        return token

    async def _api_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        access_token = token or await self._get_access_token()
        kwargs: dict[str, Any] = {
            "headers": {
                "Authorization": f"QQBot {access_token}",
                "Content-Type": "application/json",
            }
        }
        if body is not None:
            kwargs["json"] = body
        response = await self._client.request(method, f"{API_BASE}{path}", **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        data = response.json()
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}
