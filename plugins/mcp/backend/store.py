"""Atomic configuration commits and private, explicitly edited credentials."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from shiori_sdk.files.json import atomic_save_json
from .models import (
    LaunchCredentials,
    McpConfigError,
    ServerConfig,
    ServerFile,
    StdioTransport,
)
from .configuration import validate_connection


class ServerStore:
    """A failed commit retains the previous config and referenced credentials."""

    def __init__(self, path: Path):
        self.path = path
        self.private = path.parent / "credentials"
        self.servers: dict[str, ServerConfig] = {}

    def load(self) -> None:
        """Load or migrate on publication only; never overwrite corrupt data."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (ValueError, OSError):
            raise McpConfigError("MCP 配置读取失败，原文件已保留") from None
        try:
            if isinstance(data, dict) and "schema_version" not in data:
                self._migrate(data)
            else:
                self.servers = ServerFile.model_validate(data).servers
            for config in self.servers.values():
                validate_connection(config.transport, self.credentials(config))
        except (ValidationError, KeyError, TypeError, ValueError, OSError):
            raise McpConfigError("MCP 配置或私有凭据无效，原文件已保留") from None

    def _migrate(self, data: dict) -> None:
        legacy = data["servers"]
        if not isinstance(legacy, dict):
            raise ValueError("Invalid servers")
        prepared = {
            name: (
                LaunchCredentials(command=cfg["command"], env=cfg.get("env") or {}),
                StdioTransport(cwd=cfg.get("cwd")),
            )
            for name, cfg in legacy.items()
        }
        for credentials, transport in prepared.values():
            validate_connection(transport, credentials)
        migrated = {}
        for name, (credentials, transport) in prepared.items():
            migrated[name] = ServerConfig(
                label=name,
                credential_ref=self.write_credentials(credentials),
                transport=transport,
            )
        self.commit(migrated)

    def credentials(self, config: ServerConfig) -> LaunchCredentials:
        """Read an opaque reference within the private directory."""
        if re.fullmatch(r"[a-f0-9]{32}", config.credential_ref) is None:
            raise McpConfigError("MCP 凭据引用无效")
        try:
            return LaunchCredentials.model_validate_json(
                (self.private / f"{config.credential_ref}.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError):
            raise McpConfigError("MCP 私有凭据读取失败") from None

    def write_credentials(self, credentials: LaunchCredentials) -> str:
        """Write a new record before its reference becomes visible."""
        self.private.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self.private.chmod(0o700)
        ref = uuid4().hex
        path = self.private / f"{ref}.json"
        atomic_save_json(path, credentials.model_dump())
        if os.name == "posix":
            path.chmod(0o600)
        return ref

    def commit(self, servers: dict[str, ServerConfig]) -> None:
        """Publish the new index only after the atomic write succeeds."""
        atomic_save_json(self.path, ServerFile(servers=servers).model_dump())
        self.servers = servers

    def prune_credentials(self) -> None:
        """Run after sessions close; remove discarded plaintext records."""
        used = {config.credential_ref for config in self.servers.values()}
        for path in self.private.glob("*.json"):
            if path.stem not in used:
                path.unlink()
