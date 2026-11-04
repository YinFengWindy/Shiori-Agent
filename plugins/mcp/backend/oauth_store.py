"""Private OAuth persistence with durable epochs and absolute token expiry."""

import os
from pathlib import Path
from typing import Callable

from mcp.client.auth.oauth2 import OAuthContext
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from pydantic import BaseModel, Field
from shiori_sdk.files.json import atomic_save_json

from .models import LoginRequired, McpConfigError


class OAuthRecord(BaseModel):
    """Only metadata validated by the pinned provider is persisted with tokens."""

    epoch: int = 0
    tokens: OAuthToken | None = None
    client: OAuthClientInformationFull | None = None
    expires_at: float | None = None
    issuer: str | None = None
    metadata: OAuthMetadata | None = None
    resource: ProtectedResourceMetadata | None = None
    retired_secrets: list[str] = Field(default_factory=list)


class OAuthStore:
    """Synchronous atomic updates cannot interleave with invalidation in this loop."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.record = OAuthRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            self.record = OAuthRecord()
        except (ValueError, OSError):
            raise McpConfigError("OAuth 凭据读取失败，原文件已保留") from None

    def write(self, record: OAuthRecord) -> None:
        """Commit before publishing the new in-memory auth version."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self.path.parent.chmod(0o700)
        atomic_save_json(self.path, record.model_dump(mode="json"))
        if os.name == "posix":
            self.path.chmod(0o600)
        self.record = record

    def invalidate(self, *, clear: bool) -> None:
        """Reject all earlier callbacks, including if a cancelled provider finishes late."""
        record = self.record.model_copy(deep=True)
        record.epoch += 1
        if clear:
            record.tokens = None
            record.expires_at = None
            record.retired_secrets = []
        # Revocation is fail-closed in memory even if durable cleanup fails.
        # Earlier EpochStorage instances must never remain writable on I/O error.
        self.record = record
        self.write(record)

    def secrets(self) -> list[str]:
        """Include rotated tokens for responses that raced with a refresh."""
        record = self.record
        return [
            *record.retired_secrets,
            record.tokens.access_token if record.tokens else "",
            (record.tokens.refresh_token or "") if record.tokens else "",
            (record.client.client_secret or "") if record.client else "",
        ]


class EpochStorage:
    """Implement the official TokenStorage contract bound to one auth epoch."""

    def __init__(self, store: OAuthStore, changed: Callable[[], None]):
        self.store, self.epoch, self.changed = store, store.record.epoch, changed
        self.context: OAuthContext | None = None

    def check(self) -> None:
        """Late writes and requests cannot restore a revoked account."""
        if self.store.record.epoch != self.epoch:
            raise LoginRequired()

    async def get_tokens(self) -> OAuthToken | None:
        self.check()
        return self.store.record.tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        self.check()
        return self.store.record.client

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.check()
        record = self.store.record.model_copy(deep=True)
        record.client = client_info
        self.store.write(record)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.check()
        assert self.context is not None
        record = self.store.record.model_copy(deep=True)
        record.retired_secrets = self.store.secrets()[-16:]
        record.tokens = tokens
        record.expires_at = self.context.token_expiry_time
        record.issuer = self.context.auth_server_url
        record.metadata = self.context.oauth_metadata
        record.resource = self.context.protected_resource_metadata
        self.store.write(record)
        self.changed()
