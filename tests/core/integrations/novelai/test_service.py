from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from core.integrations.novelai.client import NovelAIClient
from core.integrations.novelai.models import GenerateImageRequest, NovelAISettings
from core.integrations.novelai.service import NovelAIService
from core.integrations.novelai.store import NovelAIStore
from core.roles.store import RoleStore

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sXkD1gAAAAASUVORK5CYII="
)


class _FakeClient(NovelAIClient):
    def __init__(self, response: httpx.Response, settings: NovelAISettings) -> None:
        self._response = response
        self._user_data: dict[str, object] = {}
        self.last_generate_kwargs: dict[str, object] = {}
        super().__init__(requester=None, settings=settings)  # type: ignore[arg-type]

    async def generate_image(self, **kwargs: object) -> httpx.Response:
        self.last_generate_kwargs = dict(kwargs)
        return self._response

    async def fetch_user_data(self) -> dict[str, object]:
        return self._user_data


def _json_response() -> httpx.Response:
    request = httpx.Request("POST", "https://image.novelai.net/ai/generate-image")
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"images": [base64.b64encode(_TINY_PNG).decode("utf-8")]},
        request=request,
    )


def _error_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://image.novelai.net/ai/generate-image")
    return httpx.Response(
        status_code,
        headers={"content-type": "application/json"},
        json={"statusCode": status_code, "message": "Internal Server Error"},
        request=request,
    )


@pytest.mark.asyncio
async def test_service_persists_generated_image_and_metadata(tmp_path: Path) -> None:
    settings = NovelAISettings(enabled=True, token="novel-token")
    service = NovelAIService(
        settings=settings,
        client=_FakeClient(_json_response(), settings),
        store=NovelAIStore(tmp_path),
        role_store=RoleStore(tmp_path),
        workspace=tmp_path,
    )

    result = await service.generate(
        GenerateImageRequest(
            prompt="a girl under moonlight",
            mode="txt2img",
            negative_prompt="blurry",
            session_key="role:mira",
        )
    )

    output_path = Path(result.output_paths[0])
    assert output_path.exists()
    assert output_path.read_bytes() == _TINY_PNG
    assert Path(result.request_path).exists()
    assert Path(result.meta_path).exists()
    record = json.loads(Path(result.meta_path).read_text(encoding="utf-8"))
    assert record["mode"] == "txt2img"
    assert record["prompt"] == "a girl under moonlight"
    assert record["session_key"] == "role:mira"
    request_payload = json.loads(Path(result.request_path).read_text(encoding="utf-8"))
    assert request_payload["model"] == "nai-diffusion-4-5-curated"
    assert request_payload["parameters"]["negative_prompt"] == "blurry"
    assert request_payload["parameters"]["v4_prompt"]["caption"]["base_caption"] == "a girl under moonlight"


@pytest.mark.asyncio
async def test_service_img2img_requires_base_image_path(tmp_path: Path) -> None:
    settings = NovelAISettings(enabled=True, token="novel-token")
    service = NovelAIService(
        settings=settings,
        client=_FakeClient(_json_response(), settings),
        store=NovelAIStore(tmp_path),
        role_store=RoleStore(tmp_path),
        workspace=tmp_path,
    )

    with pytest.raises(ValueError, match="base_image_path"):
        await service.generate(
            GenerateImageRequest(
                prompt="repaint this portrait",
                mode="img2img",
            )
        )


@pytest.mark.asyncio
async def test_service_auto_writeback_updates_role_assets(tmp_path: Path) -> None:
    role_store = RoleStore(tmp_path)
    _ = role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    settings = NovelAISettings(
        enabled=True,
        token="novel-token",
        auto_writeback_role_assets=True,
    )
    service = NovelAIService(
        settings=settings,
        client=_FakeClient(_json_response(), settings),
        store=NovelAIStore(tmp_path),
        role_store=role_store,
        workspace=tmp_path,
    )

    result = await service.generate(
        GenerateImageRequest(
            prompt="character portrait",
            mode="txt2img",
            role_id="mira",
            session_key="role:mira",
        )
    )

    updated = role_store.get_role("mira")
    assert updated is not None
    assert result.wrote_back_to_role is True
    assert len(updated.illustrations) == 1
    assert updated.featured_image == updated.illustrations[0]


@pytest.mark.asyncio
async def test_service_rewrites_v45_subscription_error(tmp_path: Path) -> None:
    settings = NovelAISettings(enabled=True, token="novel-token")
    client = _FakeClient(_error_response(500), settings)
    client._user_data = {
        "subscription": {
            "active": False,
            "perks": {
                "imageGeneration": False,
            },
        },
        "information": {
            "trialImagesLeft": 30,
        },
    }
    service = NovelAIService(
        settings=settings,
        client=client,
        store=NovelAIStore(tmp_path),
        role_store=RoleStore(tmp_path),
        workspace=tmp_path,
    )

    with pytest.raises(ValueError, match="subscription.active=False"):
        await service.generate(
            GenerateImageRequest(
                prompt="moonlight portrait",
                mode="txt2img",
            )
        )


@pytest.mark.asyncio
async def test_service_uses_nsfw_model_when_switch_enabled(tmp_path: Path) -> None:
    settings = NovelAISettings(
        enabled=True,
        token="novel-token",
        nsfw_enabled=True,
    )
    client = _FakeClient(_json_response(), settings)
    service = NovelAIService(
        settings=settings,
        client=client,
        store=NovelAIStore(tmp_path),
        role_store=RoleStore(tmp_path),
        workspace=tmp_path,
    )

    _ = await service.generate(
        GenerateImageRequest(
            prompt="moonlight portrait",
            mode="txt2img",
        )
    )

    assert client.last_generate_kwargs["model"] == "nai-diffusion-4-5-full"
