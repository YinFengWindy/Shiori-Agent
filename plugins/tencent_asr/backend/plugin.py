"""Registers one independent ASR provider in the host slot."""

from shiori_sdk.voice import VoicePluginContext
from .client import TencentAsrClient
from .config import TencentAsrConfig


async def setup(ctx: VoicePluginContext) -> None:
    """Contribute this provider for exactly the plugin's active lifetime."""
    config = TencentAsrConfig.model_validate(ctx.config.as_dict())
    ctx.voice.register_asr(TencentAsrClient(config, ctx.voice.http))
