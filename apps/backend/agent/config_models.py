from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
import uuid

from core.integrations.novelai.models import NovelAISettings
from agent.voice_config import VoiceConfig
from proactive_v2.config import ProactiveConfig


@dataclass
class TelegramChannelConfig:
    token: str
    channel_name: str = "telegram"


@dataclass
class QQChannelConfig:
    bot_uin: str
    websocket_open_timeout_seconds: float = 5.0


@dataclass
class ChannelsConfig:
    telegram: TelegramChannelConfig | None = None
    qq: QQChannelConfig | None = None


@dataclass
class MemoryEmbeddingConfig:
    model: str = "text-embedding-v3"
    api_key: str = ""
    base_url: str = ""
    output_dimensionality: int | None = None


@dataclass
class MemoryConfig:
    enabled: bool = False
    engine: str = ""
    embedding: MemoryEmbeddingConfig = field(default_factory=MemoryEmbeddingConfig)


# Supported reasoning effort values persisted by model registrations.
Effort = Literal["none", "low", "high", "max"]


@dataclass(frozen=True)
class ModelRegistration:
    """One selectable chat connection and model definition."""

    id: str
    provider: str
    base_url: str
    api_key: str
    model: str
    effort: Effort = "none"


@dataclass
class WiringConfig:
    context: str = "default"
    memory: str = "default"
    toolsets: list[str] = field(
        default_factory=lambda: [
            "meta_common",
            "spawn",
            "schedule",
            "mcp",
        ]
    )


@dataclass
class Config:
    provider: str
    model: str
    api_key: str
    max_tokens: int = 8192
    max_iterations: int = 10
    memory_window: int = 40
    base_url: str | None = None
    extra_body: dict = field(default_factory=dict)
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    memory_optimizer_enabled: bool = True
    memory_optimizer_interval_seconds: int = 64800
    light_model: str = ""
    light_api_key: str = ""
    light_base_url: str = ""
    agent_model: str = ""
    agent_api_key: str = ""
    agent_base_url: str = ""
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    multimodal: bool = True
    tool_search_enabled: bool = False
    spawn_enabled: bool = True
    dev_mode: bool = False
    desktop_streaming_enabled: bool = False
    novelai: NovelAISettings = field(default_factory=NovelAISettings)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    wiring: WiringConfig = field(default_factory=WiringConfig)
    plugins: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_registrations: list[ModelRegistration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.model_registrations:
            return
        stable_key = "|".join(
            [self.provider, str(self.base_url or ""), self.model]
        )
        self.model_registrations = [
            ModelRegistration(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key)),
                provider=self.provider,
                base_url=str(self.base_url or ""),
                api_key=self.api_key,
                model=self.model,
                effort="none",
            )
        ]

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        from importlib import import_module

        return import_module("agent.config").load_config(path)


__all__ = [
    "ChannelsConfig",
    "Config",
    "MemoryConfig",
    "MemoryEmbeddingConfig",
    "Effort",
    "ModelRegistration",
    "NovelAISettings",
    "QQChannelConfig",
    "TelegramChannelConfig",
    "WiringConfig",
]
