"""Generation-owned voice slots with identity-safe scoped registrations."""

from dataclasses import dataclass
from typing import Literal

from shiori_sdk.voice import AsrProvider, TtsProvider, VoiceServiceError
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.voice_http import VoiceHttp


@dataclass(frozen=True)
class _Registration:
    plugin_id: str
    provider: AsrProvider | TtsProvider


class VoiceProviderRegistry:
    """Resolves only the requested active provider; no cross-provider fallback."""

    def __init__(self) -> None:
        self._asr: dict[str, _Registration] = {}
        self._tts: dict[str, _Registration] = {}

    def register(
        self,
        kind: Literal["asr", "tts"],
        provider: AsrProvider | TtsProvider,
        scope: EffectScope,
    ) -> None:
        """Records a contribution and ties its removal to this exact registration."""
        scope.ensure_active(f"voice:{kind}")
        provider_id = provider.info.id
        if not provider_id or provider_id != provider_id.strip():
            raise ValueError("语音 provider ID 不能为空或包含首尾空白")
        entries = self._asr if kind == "asr" else self._tts
        if provider_id in entries:
            raise ValueError(f"重复的 {kind.upper()} provider: {provider_id}")
        registration = _Registration(scope.owner, provider)
        entries[provider_id] = registration

        def unregister() -> None:
            if entries.get(provider_id) is registration:
                del entries[provider_id]

        scope.add(f"voice:{kind}:{provider_id}", unregister)

    def asr(self, provider_id: str) -> AsrProvider:
        """Returns the selected recognizer or a clear unavailable-provider error."""
        from typing import cast

        return cast(AsrProvider, self._resolve(self._asr, provider_id, "ASR"))

    def tts(self, provider_id: str) -> TtsProvider:
        """Returns the selected synthesizer or a clear unavailable-provider error."""
        from typing import cast

        return cast(TtsProvider, self._resolve(self._tts, provider_id, "TTS"))

    @staticmethod
    def _resolve(
        entries: dict[str, _Registration], provider_id: str, kind: str
    ) -> AsrProvider | TtsProvider:
        registration = entries.get(provider_id)
        if registration is None:
            raise VoiceServiceError(
                f"{kind} provider 不可用: {provider_id}，请启用对应插件",
                error_code="provider_unavailable",
            )
        return registration.provider

    def describe(self) -> list[dict[str, object]]:
        """Lists installed active providers without exposing credentials or clients."""
        result: list[dict[str, object]] = []
        for kind, entries in (("asr", self._asr), ("tts", self._tts)):
            for registration in entries.values():
                info = registration.provider.info
                result.append(
                    {
                        "id": info.id,
                        "label": info.label,
                        "kind": kind,
                        "plugin_id": registration.plugin_id,
                        "available": True,
                        "capabilities": {
                            "emotions": list(info.capabilities.emotions),
                            "voice_cloning": info.capabilities.voice_cloning,
                        },
                    }
                )
        return result


class ScopedVoiceCapability:
    """Injects the plugin's scope so providers cannot claim another owner's lifetime."""

    def __init__(self, registry: VoiceProviderRegistry, effects: EffectScope) -> None:
        self._registry = registry
        self._effects = effects
        self.http = VoiceHttp()

    def register_asr(self, provider: AsrProvider) -> None:
        """Registers this plugin's recognizer until scope disposal."""
        self._registry.register("asr", provider, self._effects)

    def register_tts(self, provider: TtsProvider) -> None:
        """Registers this plugin's synthesizer until scope disposal."""
        self._registry.register("tts", provider, self._effects)
