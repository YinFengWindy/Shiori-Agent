from dataclasses import replace

import pytest

from agent.config_models import ModelRegistration
from core.roles.model_errors import incomplete_registration_fields


@pytest.mark.parametrize(
    "url",
    ["http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]:1234/v1"],
)
def test_local_openai_compatible_endpoint_can_omit_api_key(url):
    registration = ModelRegistration(
        context_window_tokens=128000,
        max_output_tokens=32768,
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
        context_window_tokens=128000,
        max_output_tokens=32768,
        id="remote",
        provider="openai",
        base_url=url,
        api_key="key",
        model="model",
    )
    assert incomplete_registration_fields(registration) == ("base_url",)
