"""Pinned official api_v2 protocol with no retry and no inference read deadline."""

import httpx
from shiori_sdk.files.audio import pcm_wav_duration

from .settings import Settings


class SovitsClient:
    """The owner must serialize every weight change and synthesis on this client."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(None, connect=5),
        )

    async def close(self) -> None:
        """Release local connections after accepted work drains."""
        await self.http.aclose()

    async def health(self, settings: Settings) -> dict[str, object]:
        """Check API reachability only; upstream exposes no loaded-version health API."""
        response = await self.http.get(settings.url + "/openapi.json", timeout=5)
        response.raise_for_status()
        value = response.json()
        paths = value.get("paths", {}) if isinstance(value, dict) else {}
        if not all(
            path in paths
            for path in ["/tts", "/set_gpt_weights", "/set_sovits_weights"]
        ):
            raise ValueError("服务不支持 GPT-SoVITS api_v2")
        return {
            "reachable": True,
            "configured_version": settings.version,
            "model_verified": False,
        }

    async def synthesize(self, settings: Settings, payload: dict[str, object]) -> bytes:
        """Set both explicit weights then read a complete non-silent PCM WAV."""
        for kind, path in [
            ("gpt", settings.gpt_weights),
            ("sovits", settings.sovits_weights),
        ]:
            response = await self.http.get(
                settings.url + f"/set_{kind}_weights", params={"weights_path": path}
            )
            self._check(response)
            if response.json() != {"message": "success"}:
                raise ValueError(f"GPT-SoVITS {kind} 权重加载未确认成功")
        response = await self.http.post(settings.url + "/tts", json=payload)
        self._check(response)
        pcm_wav_duration(response.content, require_signal=True)
        return response.content

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_error:
            # Preserve official diagnostics, including non-JSON failures, at the plugin boundary.
            raise ValueError(
                f"GPT-SoVITS HTTP {response.status_code}: {response.text[:1000]}"
            )
        response.raise_for_status()
