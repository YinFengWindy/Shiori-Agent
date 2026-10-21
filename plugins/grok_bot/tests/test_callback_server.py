import httpx
import pytest
from plugins.grok_bot.backend.callback_server import CallbackServer


async def test_authentication_path_origin_and_body_limits_before_admission():
    calls = []

    async def receive(operation, payload):
        calls.append((operation, payload))
        return 202, {"status": "accepted"}

    server = CallbackServer("one", "secret", receive)
    await server.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            for path, headers, payload, expected in [
                ("one", {}, {}, 401),
                ("other", {"Authorization": "Bearer secret"}, {}, 404),
                (
                    "one",
                    {"Authorization": "Bearer secret", "Origin": "https://other.test"},
                    {},
                    405,
                ),
                ("one", {"Authorization": "Bearer secret"}, {"text": "x" * 66000}, 413),
                ("one", {"Authorization": "Bearer secret"}, {"text": "hello"}, 202),
            ]:
                response = await client.post(
                    f"{base}/v1/connections/{path}/messages",
                    headers=headers,
                    json=payload,
                )
                assert response.status_code == expected
        assert calls == [("messages", {"text": "hello"})]
    finally:
        await server.stop()
    async with httpx.AsyncClient(trust_env=False) as client:
        with pytest.raises(httpx.ConnectError):
            await client.post(base, json={})
