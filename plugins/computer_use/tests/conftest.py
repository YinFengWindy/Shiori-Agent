"""Keep native calls explicit in independently installed plugin tests."""

import pytest
from shiori_mcp_client.testing import FakeMcpSession


@pytest.fixture(autouse=True)
def mcp_session_factory(monkeypatch):
    monkeypatch.setattr(
        "plugins.computer_use.backend.runtime.StdioMcpSession", FakeMcpSession
    )
