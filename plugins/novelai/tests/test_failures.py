from __future__ import annotations

import httpx
import pytest

from agent.plugin_host.bridge_events import PluginRpcError
from plugins.novelai.backend.failures import (
    NETWORK,
    NOT_CONFIGURED,
    QUOTA,
    UNAUTHORIZED,
    UPSTREAM,
    NovelAINotConfiguredError,
    NovelAIUpstreamError,
    call_with_rpc_failures,
    scrub_secret,
    to_rpc_error,
    token_readiness,
)


@pytest.mark.parametrize(
    ("token", "state", "env_name"),
    [
        ("", "missing", ""),
        ("   ", "missing", ""),
        ("${NOVELAI_TOKEN}", "placeholder", "NOVELAI_TOKEN"),
        (" ${NAI_KEY} ", "placeholder", "NAI_KEY"),
        ("pst-${PART}", "placeholder", "PART"),
        ("pst-abc123", "configured", ""),
    ],
)
def test_token_readiness_treats_unexpanded_env_placeholder_as_unset(
    token: str, state: str, env_name: str
) -> None:
    readiness = token_readiness(token)

    assert readiness.state == state
    assert readiness.env_name == env_name
    assert readiness.configured is (state == "configured")


def test_readiness_payload_names_the_missing_env_var() -> None:
    assert token_readiness("${NOVELAI_TOKEN}").to_payload() == {
        "configured": False,
        "reason": "placeholder",
        "message": "NovelAI token 引用的环境变量 NOVELAI_TOKEN 未设置",
    }
    assert token_readiness("pst-abc").to_payload() == {
        "configured": True,
        "reason": "",
        "message": "",
    }


def test_scrub_secret_masks_every_occurrence_and_ignores_blank_secret() -> None:
    assert scrub_secret("bad token pst-abc (pst-abc)", "pst-abc") == (
        "bad token *** (***)"
    )
    assert scrub_secret("nothing to hide", "") == "nothing to hide"


def _code(error: Exception) -> str:
    mapped = to_rpc_error(error)
    assert isinstance(mapped, PluginRpcError)
    return mapped.code


def test_to_rpc_error_maps_each_failure_kind_to_a_stable_code() -> None:
    request = httpx.Request("POST", "https://image.novelai.net/ai/generate-image")

    assert _code(NovelAINotConfiguredError("x")) == NOT_CONFIGURED
    assert _code(NovelAIUpstreamError("x", status_code=401)) == UNAUTHORIZED
    assert _code(NovelAIUpstreamError("x", status_code=403)) == UNAUTHORIZED
    assert _code(NovelAIUpstreamError("x", status_code=402)) == QUOTA
    assert _code(NovelAIUpstreamError("x", status_code=500)) == UPSTREAM
    assert _code(httpx.ConnectTimeout("slow", request=request)) == NETWORK
    assert _code(httpx.ConnectError("refused", request=request)) == NETWORK
    # Input validation keeps its own message and the bridge's invalid_request code.
    assert to_rpc_error(ValueError("prompt 不能为空")) is None


def test_unauthorized_message_does_not_echo_upstream_detail() -> None:
    mapped = to_rpc_error(
        NovelAIUpstreamError("HTTP 401 - Bearer pst-secret", status_code=401)
    )

    assert mapped is not None
    assert "pst-secret" not in str(mapped)


@pytest.mark.asyncio
async def test_call_with_rpc_failures_reraises_mapped_and_passes_others() -> None:
    async def not_configured() -> None:
        raise NovelAINotConfiguredError("NovelAI token 未配置")

    async def invalid() -> None:
        raise ValueError("prompt 不能为空")

    async def ok() -> int:
        return 7

    with pytest.raises(PluginRpcError) as caught:
        await call_with_rpc_failures(not_configured())
    assert caught.value.code == NOT_CONFIGURED
    assert isinstance(caught.value.__cause__, NovelAINotConfiguredError)
    with pytest.raises(ValueError, match="prompt 不能为空"):
        await call_with_rpc_failures(invalid())
    assert await call_with_rpc_failures(ok()) == 7
