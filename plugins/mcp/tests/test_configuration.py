"""Input boundaries prevent credential disclosure and protocol/header smuggling."""

import pytest
from plugins.mcp.backend.configuration import connection_edit
from plugins.mcp.backend.models import McpConfigError


def edit(
    url="https://example.com/mcp?filter=read", headers=None, auth="none", bearer=None
):
    return connection_edit(
        {"kind": "streamable_http", "auth": auth},
        {
            "url": {"op": "replace", "value": url},
            "headers": {"op": "replace", "value": headers or {}},
            "bearer": {"op": "replace", "value": bearer},
        },
        None,
    )


def test_url_query_is_preserved_but_userinfo_and_fragment_are_rejected():
    assert edit()[1].url == "https://example.com/mcp?filter=read"
    for url in (
        "https://user:private-secret@example.com/mcp",
        "https://example.com/mcp#private-secret",
    ):
        with pytest.raises(McpConfigError) as error:
            edit(url)
        assert "private-secret" not in str(error.value)


def test_headers_cannot_smuggle_requests_or_override_mcp_protocol():
    for headers in (
        {"X-Key": "secret\r\nOther: injected"},
        {"Mcp-Session-Id": "session"},
        {"X-Key": "one", "x-key": "two"},
    ):
        with pytest.raises(McpConfigError):
            edit(headers=headers)


def test_authorization_requires_unambiguous_mode_and_valid_bearer():
    with pytest.raises(McpConfigError, match="Authorization"):
        edit(headers={"Authorization": "Basic private"}, auth="bearer", bearer="token")
    with pytest.raises(McpConfigError, match="Bearer"):
        edit(auth="bearer", bearer="token\nsecond")
    transport, credentials = edit(
        headers={"Authorization": "Basic private"}, auth="headers"
    )
    assert (
        transport.auth == "headers"
        and credentials.headers["Authorization"] == "Basic private"
    )
