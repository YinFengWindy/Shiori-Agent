from __future__ import annotations

from agent.config_models import Config
from bus.queue import MessageBus
from core.net.http import SharedHttpResources


def build_peer_agent_resources(
    config: Config,
    bus: MessageBus,
    http_resources: SharedHttpResources,
) -> tuple[None, None]:
    """Peer agent 已从正式后端架构中移除。"""
    _ = (config, bus, http_resources)
    return None, None
