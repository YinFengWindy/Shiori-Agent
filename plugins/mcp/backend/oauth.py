"""Pinned MCP 2.3 OAuth integration; registry keeps ownership of every operation."""

from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from pathlib import Path

import httpx2
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata

from .models import LaunchCredentials, LoginRequired, OAuthClientConfig
from .oauth_callback import OAuthCallback
from .oauth_store import EpochStorage, OAuthStore


class PersistentOAuthProvider(OAuthClientProvider):
    """Restore fields omitted by MCP 2.3's TokenStorage initialization."""

    def __init__(self, binding: "OAuthBinding", storage: EpochStorage):
        self.binding, self.storage = binding, storage
        options = binding.options
        metadata = OAuthClientMetadata.model_validate(
            {
                "client_name": "Shiori",
                "redirect_uris": [binding.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": options.auth_method,
            }
        )
        super().__init__(
            binding.url, metadata, storage, binding.redirect, binding.callback
        )
        storage.context = self.context

    async def _initialize(self) -> None:
        await super()._initialize()
        record = self.storage.store.record
        self.context.token_expiry_time = record.expires_at
        self.context.auth_server_url = record.issuer
        self.context.oauth_metadata = record.metadata
        self.context.protected_resource_metadata = record.resource

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        self.storage.check()
        if self.storage.store.record.tokens is None and self.binding.operation is None:
            raise LoginRequired()
        try:
            async with aclosing(super().async_auth_flow(request)) as flow:
                outgoing = await anext(flow)
                while True:
                    self.storage.check()
                    response = yield outgoing
                    self.storage.check()
                    try:
                        outgoing = await flow.asend(response)
                    except StopAsyncIteration:
                        break
        except Exception:
            self.binding.required = True
            self.binding.changed()
            raise


class OAuthBinding:
    """One provider and refresh lock shared by live and temporary sessions."""

    def __init__(
        self, path: Path, credentials: LaunchCredentials, changed: Callable[[], None]
    ):
        self.url = credentials.url or ""
        self.options = credentials.oauth or OAuthClientConfig()
        self.redirect_uri = f"http://127.0.0.1:{self.options.redirect_port}/callback"
        self.store = OAuthStore(path)
        self.changed = changed
        self.required = self.store.record.tokens is None
        self.private_values: set[str] = set(self.store.secrets())
        self.listener: OAuthCallback | None = None
        self.operation: dict[str, object] | None = None
        self.provider = self._provider()

    def _provider(self) -> PersistentOAuthProvider:
        if self.options.client_id and self.store.record.client is None:
            record = self.store.record.model_copy(deep=True)
            record.client = OAuthClientInformationFull.model_validate(
                {
                    "client_id": self.options.client_id,
                    "client_secret": self.options.client_secret,
                    "redirect_uris": [self.redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": self.options.auth_method,
                }
            )
            self.store.write(record)
        return PersistentOAuthProvider(
            self, EpochStorage(self.store, self._token_changed)
        )

    def _token_changed(self) -> None:
        self.private_values.update(self.store.secrets())
        self.required = False
        self.changed()

    def invalidate(self, *, clear: bool = False) -> None:
        """Retire the provider before closing any network work."""
        if self.operation:
            self.operation.pop("authorization_url", None)
        self.operation = None
        self.required = clear or self.store.record.tokens is None
        self.store.invalidate(clear=clear)
        self.provider = self._provider()

    async def begin(self, operation: dict[str, object]) -> None:
        """Only a user-started login operation can open the callback channel."""
        self.invalidate(clear=True)
        self.listener = OAuthCallback(self.options.redirect_port)
        await self.listener.start()
        self.operation = operation

    async def finish(self) -> None:
        """Revoke interactive permission even while the connected session remains alive."""
        if self.operation:
            self.operation.pop("authorization_url", None)
        self.operation = None
        listener, self.listener = self.listener, None
        if listener:
            await listener.close()

    async def redirect(self, url: str) -> None:
        """A refresh failure must never open a browser in the background."""
        if (
            not self.operation
            or self.operation.get("status") != "running"
            or not self.listener
        ):
            self.required = True
            self.changed()
            raise LoginRequired()
        self.operation["authorization_url"] = url
        self.changed()

    async def callback(self):
        """Keep the issuer field intact for the official provider's validation."""
        if not self.operation or not self.listener:
            raise LoginRequired()
        result = await self.listener.wait()
        if result.code:
            self.private_values.add(result.code)
        return result

    def refresh(self) -> None:
        """Force the provider's next request to use its ordinary serialized refresh flow."""
        if not self.store.record.tokens or not self.store.record.tokens.refresh_token:
            self.required = True
            raise LoginRequired()
        record = self.store.record.model_copy(deep=True)
        record.expires_at = 1.0
        self.store.write(record)
        self.provider.context.token_expiry_time = 1.0

    def secrets(self) -> list[str]:
        """Read only this binding; retain secrets needed by its in-flight replies."""
        return [*self.store.secrets(), *self.private_values]

    def snapshot(self) -> dict[str, object]:
        """Return status and the public redirect URI, never account credentials."""
        return {
            "status": (
                "logging_in"
                if self.operation
                else "login_required" if self.required else "authorized"
            ),
            "redirect_uri": self.redirect_uri,
            "client_configured": bool(self.options.client_id),
        }
