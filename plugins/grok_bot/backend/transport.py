"""One-shot Grok Routine POSTs; uncertain writes are never retried automatically."""

import asyncio
from typing import Any

import httpx
from shiori_sdk.accounts.targets import UncertainDeliveryError


class WebhookRejectedError(ValueError):
    """A safe HTTP failure category without request or response secrets."""

    def __init__(self, status: int) -> None:
        if status in {401, 403}:
            reason = "认证失败"
        elif status == 404:
            reason = "地址不存在"
        elif status == 429:
            reason = "请求过于频繁"
        elif status >= 500:
            reason = "服务暂不可用"
        else:
            reason = "拒绝请求"
        super().__init__(f"Grok Webhook {reason}（HTTP {status}）")


class WebhookTransport:
    """Own a no-retry client for a transport with no documented idempotency key."""

    def __init__(
        self,
        url: str,
        key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url, self._key = url, key
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def start(self) -> None:
        """Open connections only when the host starts the channel."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transport, timeout=15, follow_redirects=False
            )

    async def stop(self) -> None:
        """Release all pooled connections after accepted channel work drains."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def post(self, payload: dict[str, Any]) -> None:
        """A 200 is acceptance, not completion; never invent a platform message ID."""
        if self._client is None:
            raise RuntimeError("Grok 连接尚未启动")
        try:
            async with asyncio.timeout(20):
                async with self._client.stream(
                    "POST",
                    self._url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._key}"},
                ) as response:
                    if response.status_code != 200:
                        raise WebhookRejectedError(response.status_code)
        except (httpx.TimeoutException, TimeoutError):
            raise UncertainDeliveryError(
                "Grok Webhook 请求超时，接收结果不确定"
            ) from None
        except httpx.ConnectError:
            raise UncertainDeliveryError(
                "无法连接 Grok Webhook，接收结果不确定"
            ) from None
        except httpx.TransportError:
            raise UncertainDeliveryError("Grok 发送连接中断，接收结果不确定") from None
