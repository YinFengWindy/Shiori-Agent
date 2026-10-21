"""Validated role-owned Grok connections; secrets never appear in model reprs."""

from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CHANNEL = "grok_bot"
PROTOCOL = "shiori-grok/1"
MAX_TEXT_LENGTH = 16000


class ConnectionConfig(BaseModel):
    """One role's fixed Bot endpoint and independent callback credential."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    connection_id: str
    peer_id: str
    role_id: str = Field(min_length=1)
    webhook_url: str = Field(repr=False)
    webhook_key: str = Field(min_length=1, repr=False)
    callback_token: str = Field(min_length=32, repr=False)
    peer_name: str = "Grok Bot"
    enabled: bool = True
    callback_port: int = Field(default=0, ge=0, le=65535)
    max_messages: int = Field(default=12, ge=2, le=100)
    response_rules: dict[str, object] | None = None

    @field_validator("connection_id", "peer_id")
    @classmethod
    def identifier(cls, value: str) -> str:
        """Only generated UUID hex IDs can become file or channel components."""
        if UUID(value).hex != value:
            raise ValueError("连接标识无效")
        return value

    @field_validator("webhook_url")
    @classmethod
    def webhook(cls, value: str) -> str:
        """Require a credential-free HTTPS endpoint; redirects are never followed."""
        value = value.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Webhook 必须是无查询参数和内嵌凭据的 HTTPS 地址")
        return value

    @property
    def channel_name(self) -> str:
        """Stable transport name for this role's endpoint."""
        return f"{CHANNEL}_{self.connection_id}"

    @property
    def chat_id(self) -> str:
        """Separate histories when the user switches the destination webhook."""
        return f"dm:{self.peer_id}"


def read_connection(value: object) -> ConnectionConfig:
    """Validate stored data without rendering secret input in an exception."""
    try:
        return ConnectionConfig.model_validate(value)
    except ValidationError as error:
        fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
        raise ValueError(f"Grok 连接配置无效：{', '.join(fields)}") from None
