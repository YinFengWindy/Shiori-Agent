from __future__ import annotations

from agent.config_models import Config
from infra.providers.llm_provider import LLMProvider
from core.roles.model_errors import (
    ModelConfigurationError,
    incomplete_registration_fields,
)
from bootstrap.runtime.construction import track_build_resource

_MAIN_PROVIDER_TIMEOUT_S = 45.0
_LIGHT_PROVIDER_TIMEOUT_S = 45.0
_MAIN_STREAM_IDLE_TIMEOUT_S = 45.0
_LIGHT_STREAM_IDLE_TIMEOUT_S = 45.0


class UnconfiguredProvider(LLMProvider):
    """Keeps local services available while rejecting model-dependent work."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def input_budget(self, **request):
        """Reject incomplete configuration before any prompt or network work."""
        raise ModelConfigurationError(reason=self._reason, role_id="", purpose="chat")

    async def chat(self, *args, **kwargs):
        """Reports missing configuration at the actual model invocation boundary."""
        raise ModelConfigurationError(reason=self._reason, role_id="", purpose="chat")

    async def aclose(self) -> None:
        """An unavailable provider owns no network resources."""


def build_providers(
    config: Config,
) -> tuple[LLMProvider, LLMProvider | None, LLMProvider | None]:
    """Builds the global provider without inventing a default model registration."""
    if not config.model_registrations:
        return UnconfiguredProvider("no_models"), None, None
    if incomplete_registration_fields(config.model_registrations[0]):
        return UnconfiguredProvider("connection_incomplete"), None, None
    payload_snapshot_enabled = bool(getattr(config, "dev_mode", False))
    main_extra = _sanitize_extra_body(
        base_url=config.base_url,
        extra_body=config.extra_body,
    )
    provider = LLMProvider(
        api_key=config.api_key,
        base_url=config.base_url,
        extra_body=main_extra,
        request_timeout_s=_MAIN_PROVIDER_TIMEOUT_S,
        stream_idle_timeout_s=_MAIN_STREAM_IDLE_TIMEOUT_S,
        provider_name=config.provider,
        payload_snapshot_enabled=payload_snapshot_enabled,
        context_window_tokens=config.model_registrations[0].context_window_tokens,
        max_output_tokens=config.model_registrations[0].max_output_tokens,
        budget_policy=config.context_budget,
    )
    track_build_resource(provider, provider.aclose)

    return provider, None, None


def _sanitize_extra_body(base_url: str | None, extra_body: dict | None) -> dict:
    cleaned = dict(extra_body or {})
    url = (base_url or "").lower()
    if "minimaxi.com" in url:
        cleaned.pop("enable_thinking", None)
    return cleaned
