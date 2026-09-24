"""Verifies a draft model registration with one minimal, non-persisted request.

The renderer sends the unsaved registration fields; nothing is written to the
settings file or cached. The probe goes through the same ``LLMProvider`` (and
therefore the same OpenAI-compatible client and provider strategies) that a
real chat turn uses, so a success here means the saved registration can talk
to the endpoint. Failures are reported as a scrubbed one-line summary because
the text is shown on screen and upstream errors may echo credentials.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agent.config_models import ModelRegistration
from agent.provider import LLMProvider
from core.common.error_summary import summarize_exception_for_user
from core.roles.model_errors import incomplete_registration_fields

PROBE_TIMEOUT_S = 20.0
"""Stays below the Electron bridge's 30s default request deadline."""

_PROBE_MAX_TOKENS = 8
_FIELD_LABELS = {
    "provider": "服务商",
    "model": "模型",
    "api_key": "API Key",
    "base_url": "Base URL",
}

ProviderFactory = Callable[..., LLMProvider]


def _registration_from_payload(payload: dict[str, Any]) -> ModelRegistration:
    return ModelRegistration(
        id="connection-probe",
        provider=str(payload.get("provider") or "").strip(),
        base_url=str(payload.get("base_url") or "").strip(),
        api_key=str(payload.get("api_key") or "").strip(),
        model=str(payload.get("model") or "").strip(),
    )


async def probe_model_connection(
    payload: dict[str, Any],
    *,
    provider_factory: ProviderFactory = LLMProvider,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Sends one tiny completion; returns ``ok`` plus latency or a safe reason.

    Incomplete fields raise ``ValueError`` (a request error), while an endpoint
    that rejects or never answers is an expected outcome reported as
    ``{"ok": False, "message": ...}``.
    """
    registration = _registration_from_payload(payload)
    missing = incomplete_registration_fields(registration)
    if missing:
        labels = "、".join(_FIELD_LABELS[name] for name in missing)
        raise ValueError(f"请先填写有效的{labels}")
    provider = provider_factory(
        api_key=registration.api_key,
        base_url=registration.base_url or None,
        provider_name=registration.provider,
        request_timeout_s=timeout_s,
        max_retries=0,
        payload_snapshot_enabled=False,
    )
    started = time.monotonic()
    try:
        # Auxiliary purpose keeps the probe short: reasoning is disabled or
        # dropped per provider strategy, so only reachability, credentials and
        # the model name are exercised.
        await provider.chat(
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            model=registration.model,
            max_tokens=_PROBE_MAX_TOKENS,
            call_purpose="auxiliary",
        )
    except TimeoutError:
        return {"ok": False, "message": f"{timeout_s:g} 秒内没有响应"}
    except Exception as error:
        message = summarize_exception_for_user(error)
        # Pattern-based scrubbing cannot recognise every key shape; the exact
        # submitted key is known here, so remove any echo of it verbatim.
        if len(registration.api_key) >= 4:
            message = message.replace(registration.api_key, "***REDACTED***")
        return {"ok": False, "message": message}
    finally:
        await provider.aclose()
    return {"ok": True, "latency_ms": round((time.monotonic() - started) * 1000)}


__all__ = ["PROBE_TIMEOUT_S", "probe_model_connection"]
