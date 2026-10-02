import json

import httpx
import pytest

from plugins.default_memory.backend.semantic.embedder import Embedder


class _Requester:
    def __init__(self, handler):
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def post(self, url, *, headers, json, timeout_s, budget):
        assert budget.total_timeout_s == 40.0
        return await self.client.post(
            url, headers=headers, json=json, timeout=timeout_s
        )


def _build_requester(handler):
    return _Requester(handler)


@pytest.mark.asyncio
async def test_embedder_uses_injected_requester():
    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["input"] == ["first", "second"]
        assert "dimensions" not in payload
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2, 0.3]},
                    {"index": 0, "embedding": [0.0, 0.1]},
                ]
            },
        )

    requester = _build_requester(_handler)
    try:
        embedder = Embedder(
            base_url="https://embeddings.example.com/v1",
            api_key="test-key",
            requester=requester,
        )
        vectors = await embedder.embed_batch(["first", "second"])
        assert vectors == [[0.0, 0.1], [0.2, 0.3]]
    finally:
        await requester.client.aclose()


@pytest.mark.asyncio
async def test_embedder_sends_configured_output_dimension():
    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["dimensions"] == 768
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    requester = _build_requester(_handler)
    try:
        embedder = Embedder(
            base_url="https://embeddings.example.com/v1",
            api_key="test-key",
            output_dimensionality=768,
            requester=requester,
        )
        vectors = await embedder.embed_batch(["first"])
        assert vectors == [[0.1, 0.2]]
    finally:
        await requester.client.aclose()
