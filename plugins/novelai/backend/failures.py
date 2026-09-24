"""NovelAI readiness and failure classification.

The runtime config loader leaves a ``${VAR}`` placeholder in place when the
environment variable is missing, so an "unset" token can arrive either empty
or as that literal text. Both mean 「未配置」: the service refuses before any
upstream request, and the RPC boundary tells the desktop UI which kind of
failure it is (stable ``code``) with a message that never carries the token.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Literal, TypeVar

import httpx

from agent.plugin_host.bridge_events import PluginRpcError

TokenState = Literal["configured", "missing", "placeholder"]
T = TypeVar("T")

_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")

# Stable failure codes the desktop UI maps to its own copy and actions.
NOT_CONFIGURED = "novelai_not_configured"
UNAUTHORIZED = "novelai_unauthorized"
QUOTA = "novelai_quota"
NETWORK = "novelai_network"
UPSTREAM = "novelai_upstream"


@dataclass(frozen=True)
class TokenReadiness:
    """Whether the configured token can be sent upstream, and why not."""

    state: TokenState
    env_name: str = ""

    @property
    def configured(self) -> bool:
        return self.state == "configured"

    def message(self) -> str:
        if self.state == "placeholder":
            return f"NovelAI token 引用的环境变量 {self.env_name} 未设置"
        if self.state == "missing":
            return "NovelAI token 未配置"
        return ""

    def to_payload(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "reason": "" if self.configured else self.state,
            "message": self.message(),
        }


def token_readiness(token: str) -> TokenReadiness:
    """Classifies a resolved token; an unexpanded ``${VAR}`` counts as unset."""

    text = token.strip()
    if not text:
        return TokenReadiness("missing")
    placeholder = _PLACEHOLDER.search(text)
    if placeholder:
        return TokenReadiness("placeholder", placeholder.group(1))
    return TokenReadiness("configured")


class NovelAINotConfiguredError(ValueError):
    """Raised before any upstream call when no usable token is configured."""


class NovelAIUpstreamError(ValueError):
    """An HTTP failure reported by NovelAI, already scrubbed of the token."""

    def __init__(self, message: str, *, status_code: int | None) -> None:
        super().__init__(message)
        self.status_code = status_code


def scrub_secret(text: str, secret: str) -> str:
    """Removes the token (if any) from text that may echo request details."""

    secret = secret.strip()
    if not secret or secret not in text:
        return text
    return text.replace(secret, "***")


def to_rpc_error(error: Exception) -> PluginRpcError | None:
    """Maps a generation failure to a coded RPC error; None leaves it unchanged."""

    if isinstance(error, NovelAINotConfiguredError):
        return PluginRpcError(NOT_CONFIGURED, str(error))
    if isinstance(error, NovelAIUpstreamError):
        if error.status_code in (401, 403):
            return PluginRpcError(
                UNAUTHORIZED,
                f"NovelAI 拒绝了当前 token（HTTP {error.status_code}）",
            )
        if error.status_code == 402:
            return PluginRpcError(QUOTA, "NovelAI 账户订阅或额度不足（HTTP 402）")
        return PluginRpcError(UPSTREAM, str(error))
    if isinstance(error, httpx.TimeoutException):
        return PluginRpcError(NETWORK, "连接 NovelAI 超时")
    if isinstance(error, httpx.TransportError):
        return PluginRpcError(NETWORK, "无法连接 NovelAI")
    return None


async def call_with_rpc_failures(awaitable: Awaitable[T]) -> T:
    """Awaits one generation, re-raising known failures as coded RPC errors."""

    try:
        return await awaitable
    except Exception as exc:
        mapped = to_rpc_error(exc)
        if mapped is None:
            raise
        raise mapped from exc
