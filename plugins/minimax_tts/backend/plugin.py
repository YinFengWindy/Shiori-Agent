"""Registers one independent TTS provider in the host slot."""

from shiori_sdk.voice import VoicePluginContext
from .client import MiniMaxTtsClient
from .config import MiniMaxTtsConfig


async def setup(ctx: VoicePluginContext) -> None:
    """Contribute this provider for exactly the plugin's active lifetime."""
    config = MiniMaxTtsConfig.model_validate(ctx.config.as_dict())
    ctx.voice.register_tts(MiniMaxTtsClient(config, ctx.voice.http))
