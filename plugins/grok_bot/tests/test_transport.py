import httpx
import pytest
from shiori_sdk.accounts.targets import UncertainDeliveryError
from plugins.grok_bot.backend.transport import WebhookTransport


@pytest.mark.parametrize("status", [200, 202, 302, 401, 500])
async def test_only_200_means_accepted_and_no_http_failure_is_retried(status):
    calls = []

    def remote(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://other.test/secret"},
            json={"runUuid": "run"},
        )

    transport = WebhookTransport(
        "https://example.test/routine", "secret", transport=httpx.MockTransport(remote)
    )
    transport.start()
    try:
        if status == 200:
            assert await transport.post({"text": "hi"}) is None
        else:
            with pytest.raises(ValueError, match="Webhook"):
                await transport.post({"text": "hi"})
        assert len(calls) == 1
    finally:
        await transport.stop()


async def test_timeout_is_uncertain_and_never_retried():
    calls = []

    def remote(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret-bearing-network-error")

    transport = WebhookTransport(
        "https://example.test/routine", "secret", transport=httpx.MockTransport(remote)
    )
    transport.start()
    try:
        with pytest.raises(UncertainDeliveryError) as raised:
            await transport.post({"text": "hi"})
        assert "secret-bearing" not in str(raised.value)
        assert len(calls) == 1
    finally:
        await transport.stop()
