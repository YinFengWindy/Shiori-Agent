from unittest.mock import AsyncMock, MagicMock

from agent.config_models import Config, ModelRegistration
from bootstrap.providers import build_providers


def test_bootstrap_providers_set_a_shared_request_budget(monkeypatch):
    provider = MagicMock(aclose=AsyncMock())
    create_provider = MagicMock(return_value=provider)
    monkeypatch.setattr("bootstrap.providers.LLMProvider", create_provider)
    config = Config(
        provider="openai",
        model="main",
        api_key="main-key",
        base_url="https://example.com/v1",
        light_model="light",
        light_api_key="light-key",
        light_base_url="https://light.example.com/v1",
        agent_model="agent",
        agent_api_key="agent-key",
        agent_base_url="https://agent.example.com/v1",
        multimodal=False,
        model_registrations=[
            ModelRegistration(
                id="main",
                provider="openai",
                model="main",
                api_key="main-key",
                base_url="https://example.com/v1",
                context_window_tokens=128000,
                max_output_tokens=32768,
            )
        ],
    )

    main, light, agent = build_providers(config)

    create_provider.assert_called_once()
    assert create_provider.call_args.kwargs["request_timeout_s"] == 45.0
    assert create_provider.call_args.kwargs["stream_idle_timeout_s"] == 45.0
    assert create_provider.call_args.kwargs["api_key"] == "main-key"
    assert main is provider
    assert light is None and agent is None


async def test_incomplete_provider_preflight_preserves_configuration_error():
    import pytest
    from core.roles.model_errors import ModelConfigurationError

    # Legacy inferred registration deliberately has no capacity guesses.
    provider, _, _ = build_providers(
        Config(provider="openai", model="legacy", api_key="test")
    )
    request = dict(messages=[], tools=[], model="legacy", max_tokens=10)
    with pytest.raises(ModelConfigurationError, match="需补填"):
        provider.input_budget(**request)
    with pytest.raises(ModelConfigurationError, match="需补填"):
        await provider.chat(**request)
