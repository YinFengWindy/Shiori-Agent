"""Local service origins must not silently send audio to remote/proxied origins."""

import pytest
from shiori_sdk.local_http import loopback_http_url


@pytest.mark.parametrize(
    "value", ["http://127.0.0.1:9880", "http://localhost:8000", "http://[::1]:9880/"]
)
def test_explicit_loopback(value):
    assert loopback_http_url(value) == value.rstrip("/")


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://192.168.1.2",
        "http://127.0.0.1/path",
        "http://u:p@localhost",
        "http://localhost?x=1",
        "http://localhost:abc",
    ],
)
def test_rejects_non_origin_or_non_local_url(value):
    with pytest.raises(ValueError):
        loopback_http_url(value)
