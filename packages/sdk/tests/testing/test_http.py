"""HTTP fakes answer only through a configured handler and record each request."""

import httpx
import pytest

from shiori_sdk.http import ResponseTooLarge
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


@pytest.mark.parametrize("request_method", ["get", "request"])
async def test_fake_download_enforces_optional_response_cap(
    request_method: str,
) -> None:
    http = FakeChannelHttp(lambda _: httpx.Response(200, content=b"12345"))

    with pytest.raises(ResponseTooLarge):
        if request_method == "get":
            _ = await http.get("https://x.test", max_response_bytes=4)
        else:
            _ = await http.request("GET", "https://x.test", max_response_bytes=4)
    response = await http.get("https://x.test", max_response_bytes=5)

    assert response.content == b"12345"


async def test_fake_download_rejects_advertised_size() -> None:
    http = FakeHttp(
        lambda _: httpx.Response(200, headers={"content-length": "20"}, content=b"1")
    )

    with pytest.raises(ResponseTooLarge):
        _ = await http.get("https://x.test", max_response_bytes=4)
