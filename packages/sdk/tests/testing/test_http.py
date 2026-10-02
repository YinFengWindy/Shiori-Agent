"""HTTP fakes answer only through a configured handler and record each request."""

import httpx
import pytest

from shiori_sdk.testing.http import FakeChannelHttp, FakeHttp, FakeHttpResources


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=f"{request.method} {request.url}")


async def test_channel_http_dispatches_any_method_through_its_handler() -> None:
    http = FakeChannelHttp(_ok)

    response = await http.request("PUT", "https://x.test/a", headers={"k": "v"})
    fetched = await http.get("https://x.test/b")

    assert response.text == "PUT https://x.test/a"
    assert response.request.headers["k"] == "v"
    assert fetched.text == "GET https://x.test/b"
    assert [(r.method, str(r.url)) for r in http.requests] == [
        ("PUT", "https://x.test/a"),
        ("GET", "https://x.test/b"),
    ]


async def test_unconfigured_requests_fail_at_the_transport_boundary() -> None:
    with pytest.raises(AssertionError, match="Unconfigured HTTP GET"):
        await FakeHttp().get("https://x.test")
    with pytest.raises(AssertionError, match="Unconfigured HTTP DELETE"):
        await FakeChannelHttp().request("DELETE", "https://x.test")


async def test_resources_default_to_profiles_that_refuse_requests() -> None:
    external = FakeChannelHttp(_ok)
    resources = FakeHttpResources(external_default=external)

    assert resources.external_default is external
    with pytest.raises(AssertionError, match="Unconfigured HTTP GET"):
        await resources.local_service.get("http://127.0.0.1")
