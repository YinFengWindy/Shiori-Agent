"""Versioned server intent and private connection material."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    """Reject malformed persistent records without silently dropping fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ToolSelection(Record):
    """An empty selected set deliberately exposes no tools."""

    mode: Literal["all", "selected"] = "all"
    names: list[str] = Field(default_factory=list)

    def allows(self, name: str) -> bool:
        """Evaluate discovery and execution against the same selection."""
        return self.mode == "all" or name in self.names


class StdioTransport(Record):
    """Public settings; argv and env live in the private record."""

    kind: Literal["stdio"] = "stdio"
    cwd: str | None = None


class HttpTransport(Record):
    """HTTP intent; the complete URL and authentication values stay private."""

    kind: Literal["streamable_http"] = "streamable_http"
    auth: Literal["none", "bearer", "headers"] = "none"


Transport = Annotated[StdioTransport | HttpTransport, Field(discriminator="kind")]


class ServerConfig(Record):
    """Saved intent, independent of whether a connection succeeds."""

    label: str
    revision: int = Field(default=1, ge=1)
    enabled: bool = True
    transport: Transport = Field(default_factory=StdioTransport)
    tools: ToolSelection = Field(default_factory=ToolSelection)
    credential_ref: str


class ServerFile(Record):
    """The only persisted server index."""

    schema_version: Literal[2] = 2
    servers: dict[str, ServerConfig] = Field(default_factory=dict)


class LaunchCredentials(Record):
    """Private material, including command arguments which may contain secrets."""

    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    bearer: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class McpConfigError(ValueError):
    """A safe validation message, without Pydantic input values."""
