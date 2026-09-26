"""Minimal async client for the Feishu / Lark open platform REST API."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from .formatting import as_dict, as_list

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 230020 is the documented IM frequency limit, 99991400 the generic gateway
# limit and 11232 the burst limit seen at full and half hours.
RATE_LIMIT_CODES = frozenset({230020, 99991400, 11232})
# The tenant token was revoked or expired early; fetching a new one fixes it.
INVALID_TOKEN_CODES = frozenset({99991661, 99991663, 99991668})
RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_S = 0.5
RETRY_MAX_DELAY_S = 8.0
TOKEN_REFRESH_MARGIN_S = 300


class FeishuApiError(RuntimeError):
    """A Feishu API call answered with a nonzero business ``code``."""

    def __init__(self, code: int, msg: str, *, http_status: int = 200) -> None:
        super().__init__(f"飞书 API 失败 code={code} msg={msg}")
        self.code = code
        self.http_status = http_status


def is_rate_limited(error: BaseException) -> bool:
    """Returns whether retrying ``error`` later can succeed."""
    if isinstance(error, FeishuApiError):
        return error.code in RATE_LIMIT_CODES or error.http_status == 429
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429
    return False


class FeishuApi:
    """Owns the tenant token and the HTTP client for one app credential."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._base = domain.rstrip("/")
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._token = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def open(self) -> None:
        """Creates the HTTP client; reopening after :meth:`aclose` is allowed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, transport=self._transport)

    async def aclose(self) -> None:
        """Closes the HTTP client; safe to call repeatedly."""
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            raise RuntimeError("飞书 API 客户端尚未打开")
        return self._client

    async def tenant_token(self) -> str:
        """Returns a cached ``tenant_access_token``, refreshing it near expiry."""
        async with self._token_lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            response = await self._require_client().post(
                f"{self._base}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            payload = _checked_payload(response)
            self._token = str(payload.get("tenant_access_token") or "")
            if not self._token:
                raise RuntimeError("飞书认证响应缺少 tenant_access_token")
            expire = int(payload.get("expire") or 7200)
            self._token_expires_at = time.time() + max(
                60, expire - TOKEN_REFRESH_MARGIN_S
            )
            return self._token

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes]] | None = None,
    ) -> dict[str, Any]:
        """Calls one endpoint and returns the full JSON payload (``code`` = 0)."""
        for attempt in range(2):
            token = await self.tenant_token()
            response = await self._require_client().request(
                method,
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
                params=params,
                data=data,
                files=files,
            )
            try:
                return _checked_payload(response)
            except FeishuApiError as error:
                if attempt == 0 and error.code in INVALID_TOKEN_CODES:
                    self._token = ""
                    continue
                raise
        raise AssertionError("unreachable")

    async def download(self, path: str, *, params: dict[str, str]) -> bytes:
        """Downloads a binary resource; JSON bodies here are always errors."""
        token = await self.tenant_token()
        response = await self._require_client().get(
            f"{self._base}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if response.headers.get("content-type", "").startswith("application/json"):
            _checked_payload(response)
        response.raise_for_status()
        return response.content

    async def fetch_url(self, url: str) -> bytes:
        """Downloads a public http(s) resource, e.g. an image to re-upload."""
        response = await self._require_client().get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content

    # ── IM ────────────────────────────────────────────────────────────

    async def send_message(
        self, receive_id: str, receive_id_type: str, msg_type: str, content: str
    ) -> str:
        """Sends a message and returns its ``message_id``."""
        payload = await self.request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json_body={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
                "uuid": str(uuid.uuid4()),
            },
        )
        message_id = str(as_dict(payload.get("data")).get("message_id") or "")
        if not message_id:
            raise RuntimeError("飞书发送响应缺少 message_id")
        return message_id

    async def reply_message(self, message_id: str, msg_type: str, content: str) -> str:
        """Replies to (quotes) ``message_id`` and returns the new message id."""
        payload = await self.request(
            "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            json_body={
                "msg_type": msg_type,
                "content": content,
                "uuid": str(uuid.uuid4()),
            },
        )
        message_id = str(as_dict(payload.get("data")).get("message_id") or "")
        if not message_id:
            raise RuntimeError("飞书回复响应缺少 message_id")
        return message_id

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Returns the message item (``msg_type``, ``body``, ``sender`` …)."""
        payload = await self.request("GET", f"/open-apis/im/v1/messages/{message_id}")
        items = as_list(as_dict(payload.get("data")).get("items"))
        return as_dict(items[0]) if items else {}

    async def delete_message(self, message_id: str) -> None:
        """Recalls a message the bot sent."""
        await self.request("DELETE", f"/open-apis/im/v1/messages/{message_id}")

    async def download_resource(
        self, message_id: str, file_key: str, resource_type: str
    ) -> bytes:
        """Downloads an image or file attached to a received message."""
        return await self.download(
            f"/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
            params={"type": resource_type},
        )

    async def upload_image(self, data: bytes) -> str:
        """Uploads a message image and returns its ``image_key``."""
        payload = await self.request(
            "POST",
            "/open-apis/im/v1/images",
            data={"image_type": "message"},
            files={"image": ("image", data)},
        )
        return str(as_dict(payload.get("data")).get("image_key") or "")

    async def upload_file(self, data: bytes, file_name: str) -> str:
        """Uploads a message file and returns its ``file_key``."""
        payload = await self.request(
            "POST",
            "/open-apis/im/v1/files",
            data={"file_type": "stream", "file_name": file_name},
            files={"file": (file_name, data)},
        )
        return str(as_dict(payload.get("data")).get("file_key") or "")

    async def bot_info(self) -> dict[str, Any]:
        """Returns the bot profile (``app_name``, ``open_id``)."""
        payload = await self.request("GET", "/open-apis/bot/v3/info")
        return as_dict(payload.get("bot"))

    # ── CardKit ───────────────────────────────────────────────────────

    async def create_card(self, card_json: str) -> str:
        """Creates a card entity from JSON 2.0 and returns its ``card_id``."""
        payload = await self.request(
            "POST",
            "/open-apis/cardkit/v1/cards",
            json_body={"type": "card_json", "data": card_json},
        )
        return str(as_dict(payload.get("data")).get("card_id") or "")

    async def stream_card_text(
        self, card_id: str, element_id: str, content: str, sequence: int
    ) -> None:
        """Replaces a streaming element's full text (typewriter on the client)."""
        await self.request(
            "PUT",
            f"/open-apis/cardkit/v1/cards/{card_id}/elements/{element_id}/content",
            json_body={
                "content": content,
                "sequence": sequence,
                "uuid": str(uuid.uuid4()),
            },
        )

    async def update_card_settings(
        self, card_id: str, settings: str, sequence: int
    ) -> None:
        """Updates a card entity's ``config`` (e.g. to end streaming mode)."""
        await self.request(
            "PATCH",
            f"/open-apis/cardkit/v1/cards/{card_id}/settings",
            json_body={
                "settings": settings,
                "sequence": sequence,
                "uuid": str(uuid.uuid4()),
            },
        )

    async def update_card(self, card_id: str, card_json: str, sequence: int) -> None:
        """Replaces a card entity wholesale; works whether or not it streams."""
        await self.request(
            "PUT",
            f"/open-apis/cardkit/v1/cards/{card_id}",
            json_body={
                "card": {"type": "card_json", "data": card_json},
                "sequence": sequence,
                "uuid": str(uuid.uuid4()),
            },
        )


async def with_rate_limit_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    label: str,
    attempts: int = RETRY_ATTEMPTS,
) -> T:
    """Retries a call only while Feishu reports a frequency limit."""
    delay = RETRY_BASE_DELAY_S
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except (FeishuApiError, httpx.HTTPStatusError) as error:
            if attempt >= attempts or not is_rate_limited(error):
                raise
            logger.warning(
                "[feishu] %s 触发频控，%.1fs 后重试（%d/%d）",
                label,
                delay,
                attempt,
                attempts,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_DELAY_S)
    raise AssertionError("unreachable")


def _checked_payload(response: httpx.Response) -> dict[str, Any]:
    """Raises on a nonzero business code, else on an HTTP error status."""
    try:
        payload = as_dict(response.json())
    except (json.JSONDecodeError, ValueError):
        response.raise_for_status()
        return {}
    code = int(payload.get("code") or 0)
    if code != 0:
        raise FeishuApiError(
            code, str(payload.get("msg") or ""), http_status=response.status_code
        )
    response.raise_for_status()
    return payload
