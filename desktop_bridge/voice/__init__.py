"""Voice and text-to-speech services used by the desktop bridge."""

from .role_tts_settings import RoleTtsSettings, resolve_role_tts_settings
from .tts_coordinator import TtsTurnCoordinator
from .tts_text import TtsSentenceBuffer, split_tts_sentences
from .voice_assets import VoiceAssetLifecycle
from .voice_handler import DesktopVoiceHandler
from .voice_models import VoiceOperationMetrics, VoiceServiceError, VoiceSynthesisResult
from .voice_service import VoiceService

__all__ = [
    "DesktopVoiceHandler",
    "RoleTtsSettings",
    "TtsSentenceBuffer",
    "TtsTurnCoordinator",
    "VoiceAssetLifecycle",
    "VoiceOperationMetrics",
    "VoiceService",
    "VoiceServiceError",
    "VoiceSynthesisResult",
    "resolve_role_tts_settings",
    "split_tts_sentences",
]
