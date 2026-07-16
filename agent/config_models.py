from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.integrations.novelai.models import NovelAISettings
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


@dataclass(frozen=True)
class CodingAgentProfileConfig:
    """Validated CLI model and execution limits exposed as one named profile."""

    provider: str
    model: str
    effort: str = "medium"
    timeout_seconds: int = 1800
    max_parallel_runs: int = 1
    max_permission_level: str = "workspace-write"
    max_budget_usd: float | None = None
    command: str = ""


@dataclass(frozen=True)
class CodingAgentProjectConfig:
    """A statically trusted Git repository available to Coding Agent runs."""

    repo_path: str
    base_ref: str = "HEAD"
    retention: str = "keep"
    max_parallel_runs: int = 1


@dataclass(frozen=True)
class CodingAgentsConfig:
    """Configuration boundary for persisted Coding Agent orchestration."""

    enabled: bool = False
    worktree_root: str = ""
    default_project: str = ""
    default_profile: str = ""
    max_parallel_runs: int = 3
    profiles: dict[str, CodingAgentProfileConfig] = field(default_factory=dict)
    projects: dict[str, CodingAgentProjectConfig] = field(default_factory=dict)


@dataclass
class WiringConfig:
    context: str = "default"
    memory: str = "default"
    toolsets: list[str] = field(
        default_factory=lambda: [
            "meta_common",
            "spawn",
            "coding_agent",
            "schedule",
            "mcp",
        ]
    )


@dataclass
class Config:
    provider: str
    model: str
    api_key: str
    system_prompt: str
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
    coding_agents: CodingAgentsConfig = field(default_factory=CodingAgentsConfig)
    multimodal: bool = True
    vl_model: str = ""
    vl_api_key: str = ""
    vl_base_url: str = ""
    tool_search_enabled: bool = False
    spawn_enabled: bool = True
    dev_mode: bool = False
    novelai: NovelAISettings = field(default_factory=NovelAISettings)
    wiring: WiringConfig = field(default_factory=WiringConfig)
    plugins: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        from importlib import import_module

        return import_module("agent.config").load_config(path)


__all__ = [
    "ChannelsConfig",
    "CodingAgentProfileConfig",
    "CodingAgentProjectConfig",
    "CodingAgentsConfig",
    "Config",
    "MemoryConfig",
    "MemoryEmbeddingConfig",
    "NovelAISettings",
    "QQChannelConfig",
    "TelegramChannelConfig",
    "WiringConfig",
]
