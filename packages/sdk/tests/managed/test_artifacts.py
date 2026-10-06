"""Real streamed bytes demonstrate integrity checks and interrupted range recovery."""

import asyncio
import hashlib

import httpx
import pytest

from shiori_sdk.managed.artifacts import Artifact, acquire_artifact


def resource(data: bytes):
    return Artifact(
        "runtime.bin",
        "https://example.test/fixed",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.parametrize("range_supported", [True, False])
async def test_resumes_partial_or_restarts_when_range_ignored(
    tmp_path, range_supported
):
    data = b"fixed immutable runtime"
    path = tmp_path / "runtime.bin"
    path.with_suffix(".bin.part").write_bytes(data[:5])
    requests = []

    def respond(request):
        requests.append(request)
        if range_supported:
            return httpx.Response(
                206,
                headers={"Content-Range": f"bytes 5-{len(data)-1}/{len(data)}"},
                content=data[5:],
            )
        return httpx.Response(200, content=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await acquire_artifact(resource(data), path, lambda _: None, client=client)
    assert requests[0].headers["range"] == "bytes=5-"
    assert path.read_bytes() == data
    assert not path.with_suffix(".bin.part").exists()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(206, headers={"Content-Range": "bytes 0-4/5"}, content=b"wrong"),
        httpx.Response(200, content=b"bad-content"),
        httpx.Response(200, content=b"more bytes than the fixed size"),
    ],
)
async def test_invalid_content_never_publishes_and_discards_invalid_partial(
    tmp_path, response
):
    path = tmp_path / "runtime.bin"
    path.with_suffix(".bin.part").write_bytes(b"f")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: response)
    ) as client:
        with pytest.raises(ValueError):
            await acquire_artifact(
                resource(b"fixed-data!"), path, lambda _: None, client=client
            )
    assert not path.exists()
    assert not path.with_suffix(".bin.part").exists()


async def test_cancel_retains_partial_but_not_complete_file(tmp_path):
    data = b"x" * (2 * 1024 * 1024)
    entered = asyncio.Event()

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield data[: 1024 * 1024]
            entered.set()
            await asyncio.Event().wait()

    path = tmp_path / "runtime.bin"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=SlowStream())
        )
    ) as client:
        task = asyncio.create_task(
            acquire_artifact(resource(data), path, lambda _: None, client=client)
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not path.exists()
    assert path.with_suffix(".bin.part").stat().st_size == 1024 * 1024
