"""Pending renderer request bounds and owner cleanup."""

import pytest

from agent.plugin_host.bridge_events import PluginRpcError
from agent.plugin_host.renderer_requests import RendererRequests


@pytest.mark.asyncio
async def test_pending_requests_are_bounded_and_cancelled_by_either_owner():
    requests = RendererRequests()
    pending = [requests.create("caller", "provider")[1] for _ in range(128)]
    with pytest.raises(PluginRpcError) as failure:
        requests.create("other", "provider")
    assert failure.value.code == "plugin_busy"
    requests.cancel("caller")
    assert not requests.pending
    for request in pending:
        with pytest.raises(PluginRpcError):
            await request.future
