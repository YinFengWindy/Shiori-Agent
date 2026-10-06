"""Official FunASR HTTP protocol, with explicit CPU/model health verification."""

import httpx

from .settings import Settings


class SenseVoiceClient:
    """Own a direct local transport with no retry and a provider-owned deadline."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(60, connect=5),
        )

    async def close(self) -> None:
        """Release the plugin's HTTP connection pool."""
        await self.http.aclose()

    async def health(self, settings: Settings) -> dict[str, object]:
        """Return actual server health; reject a missing model or non-CPU deployment."""
        response = await self.http.get(settings.url + "/health", timeout=5)
        self._check(response)
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("SenseVoice 健康检查返回格式无效")
        if value.get("device") != "cpu":
            raise ValueError("SenseVoice 服务未使用 CPU，请以 --device cpu 启动")
        if value.get("status") != "ok" or "sensevoice" not in value.get(
            "models_loaded", []
        ):
            raise ValueError("SenseVoiceSmall 模型尚未加载")
        return {"device": "cpu", "model": "sensevoice", "ready": True}

    async def transcribe(self, settings: Settings, audio: bytes) -> dict[str, object]:
        """Upload a complete WAV with explicit sensevoice selection; empty text is valid."""
        response = await self.http.post(
            settings.url + "/v1/audio/transcriptions",
            files={"file": ("audio.wav", audio, "audio/wav")},
            data={"model": "sensevoice", "response_format": "json"},
        )
        self._check(response)
        value = response.json()
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            raise ValueError("SenseVoice 返回格式无效：缺少 text")
        return {"text": value["text"]}

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"SenseVoice HTTP {response.status_code}: {response.text[:1000]}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
