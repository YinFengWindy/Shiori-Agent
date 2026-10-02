from dataclasses import replace

import pytest

from agent.config_models import ModelRegistration
from core.roles.model_errors import (
    incomplete_connection_fields,
    incomplete_registration_fields,
)


@pytest.mark.parametrize(
    "url",
    ["http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]:1234/v1"],
)
def test_local_openai_compatible_endpoint_can_omit_api_key(url):
    registration = ModelRegistration(
        model_context_window=128000,
        id="local",
        provider="openai",
        base_url=url,
        api_key="",
        model="local",
    )
    assert incomplete_registration_fields(registration) == ()
    assert incomplete_registration_fields(
        replace(registration, api_key="${MISSING}")
    ) == ("api_key",)


@pytest.mark.parametrize(
    "url", ["${MISSING_URL}", "file:///tmp/model", "https://[broken"]
)
def test_invalid_connection_address_is_a_repairable_field(url):
    registration = ModelRegistration(
        model_context_window=128000,
        id="remote",
        provider="openai",
        base_url=url,
        api_key="key",
        model="model",
    )
    assert incomplete_registration_fields(registration) == ("base_url",)


def test_connection_readiness_does_not_imply_conversation_capacity_is_complete():
    legacy = ModelRegistration(
        id="legacy",
        provider="openai",
        base_url="https://example.test/v1",
        api_key="test",
        model="m",
    )
    assert incomplete_connection_fields(legacy) == ()
    assert incomplete_registration_fields(legacy) == ("model_context_window",)
    broken = replace(legacy, api_key="")
    assert incomplete_connection_fields(broken) == ("api_key",)
    assert incomplete_registration_fields(broken) == (
        "api_key",
        "model_context_window",
    )
