"""Sprite provider adapter for the shared presentation transport."""

from shiori_sdk.rpc import RpcCapability
from plugins.desktop_pet.backend.provider_presentation import ProviderPresentation
from .provider import SpriteModels


class SpritePresentation(ProviderPresentation):
    """Resolve private sprite data while sharing readiness and command validation."""

    def __init__(self, models: SpriteModels, rpc: RpcCapability) -> None:
        super().__init__(rpc, models.presentation, label="精灵")
