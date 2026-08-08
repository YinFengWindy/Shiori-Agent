from __future__ import annotations

from agent.config_models import Config
from infra.providers.llm_provider import LLMProvider

_MAIN_PROVIDER_TIMEOUT_S = 45.0
_LIGHT_PROVIDER_TIMEOUT_S = 45.0
_MAIN_STREAM_IDLE_TIMEOUT_S = 45.0
_LIGHT_STREAM_IDLE_TIMEOUT_S = 45.0


def build_providers(
    config: Config,
) -> tuple[LLMProvider, LLMProvider | None, LLMProvider | None]:
    payload_snapshot_enabled = bool(getattr(config, "dev_mode", False))
    main_extra = _sanitize_extra_body(
        base_url=config.base_url,
        extra_body=config.extra_body,
    )
    provider = LLMProvider(
        api_key=config.api_key,
        base_url=config.base_url,
        system_prompt=config.system_prompt,
        extra_body=main_extra,
        request_timeout_s=_MAIN_PROVIDER_TIMEOUT_S,
        stream_idle_timeout_s=_MAIN_STREAM_IDLE_TIMEOUT_S,
        provider_name=config.provider,
        payload_snapshot_enabled=payload_snapshot_enabled,
    )

    return provider, None, None


def build_vl_provider(config: Config) -> LLMProvider | None:
    """Compatibility entrypoint; role model runtime owns visual selection."""
    return None


def _sanitize_extra_body(base_url: str | None, extra_body: dict | None) -> dict:
    cleaned = dict(extra_body or {})
    url = (base_url or "").lower()
    if "minimaxi.com" in url:
        cleaned.pop("enable_thinking", None)
    return cleaned
