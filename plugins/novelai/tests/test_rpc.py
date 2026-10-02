from __future__ import annotations
from shiori_sdk.testing.memory import FakeMemoryStorage

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.rpc import PluginRpcError
from plugins.novelai.backend.failures import NovelAINotConfiguredError, token_readiness
from plugins.novelai.backend.models import GenerateImageResult, GeneratedImageRecord
from plugins.novelai.backend.prompt_tags import PromptTagStore
from plugins.novelai.backend.rpc import NovelAIRpcHandlers
from plugins.novelai.backend.store import NovelAIStore
from shiori_sdk.testing.services import FakeSessions as SessionManager


def _handlers(
    *,
    tmp_path: Path,
    session_manager: SessionManager | None = None,
    novelai_service=None,
    novelai_store: NovelAIStore | None = None,
    prompt_tag_store: PromptTagStore | None = None,
) -> NovelAIRpcHandlers:
    return NovelAIRpcHandlers(
        novelai_service=novelai_service,
        novelai_store=novelai_store
        or NovelAIStore(
            tmp_path, storage=FakeMemoryStorage(), original_media=lambda value: value
        ),
        prompt_tag_store=prompt_tag_store
        or PromptTagStore(tmp_path, storage=FakeMemoryStorage()),
        session_manager=session_manager or SessionManager(),
    )


@pytest.mark.asyncio
async def test_generate_derives_session_key_from_role_id(tmp_path: Path) -> None:
    novelai_service = SimpleNamespace(
        generate=AsyncMock(
            return_value=GenerateImageResult(
                record_id="rec-1",
                created_at="2026-06-30T12:00:00+00:00",
                mode="txt2img",
                model="nai-diffusion-4-5-full",
                seed=456,
                width=1024,
                height=1024,
                output_paths=[],
                request_path="request.json",
                meta_path="meta.json",
            )
        )
    )
    handlers = _handlers(tmp_path=tmp_path, novelai_service=novelai_service)

    payload = await handlers.generate(
        {"role_id": "mira", "prompt": "moonlight portrait", "mode": "txt2img"}
    )

    assert payload["result"]["record_id"] == "rec-1"
    request = novelai_service.generate.await_args.args[0]
    assert request.role_id == "mira"
    assert request.session_key == "role:mira"


def test_history_filters_by_role(tmp_path: Path) -> None:
    store = NovelAIStore(
        tmp_path, storage=FakeMemoryStorage(), original_media=lambda value: value
    )
    output_path = tmp_path / "private_runtime" / "novelai" / "outputs" / "out.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"png")
    for record_id, role_id in (("rec-1", "mira"), ("rec-2", "atlas")):
        store.append_record(
            GeneratedImageRecord(
                id=record_id,
                created_at="2026-06-30T10:00:00+00:00",
                mode="txt2img",
                role_id=role_id,
                session_key=f"role:{role_id}",
                prompt="p",
                negative_prompt="",
                model="nai-diffusion-4-5-full",
                sampler="k_euler",
                steps=28,
                seed=1,
                width=1024,
                height=1024,
                base_image_path="",
                output_paths=[str(output_path)],
                wrote_back_to_role=False,
            )
        )
    handlers = _handlers(tmp_path=tmp_path, novelai_store=store)

    result = asyncio.run(handlers.history({"role_id": "mira", "limit": 5}))

    assert [record["id"] for record in result["records"]] == ["rec-1"]


@pytest.mark.asyncio
async def test_prompt_tags_crud_round_trips_through_the_store(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path=tmp_path)

    created = await handlers.prompt_tags_upsert(
        {
            "id": "tag-1",
            "name": "Rain",
            "category": "weather",
            "match_terms": ["rain"],
            "positive_tags": ["rain"],
            "negative_tags": [],
        }
    )
    assert created["entry"]["id"] == "tag-1"

    listed = await handlers.prompt_tags_list({})
    assert [entry["id"] for entry in listed["entries"]] == ["tag-1"]

    deleted = await handlers.prompt_tags_delete({"id": "tag-1"})
    assert deleted == {}
    listed_after_delete = await handlers.prompt_tags_list({})
    assert listed_after_delete["entries"] == []


@pytest.mark.asyncio
async def test_generate_reports_missing_token_with_a_stable_code(
    tmp_path: Path,
) -> None:
    novelai_service = SimpleNamespace(
        generate=AsyncMock(
            side_effect=NovelAINotConfiguredError(
                "NovelAI token 引用的环境变量 NOVELAI_TOKEN 未设置"
            )
        )
    )
    handlers = _handlers(tmp_path=tmp_path, novelai_service=novelai_service)

    with pytest.raises(PluginRpcError) as caught:
        await handlers.generate({"role_id": "mira", "prompt": "portrait"})

    assert caught.value.code == "novelai_not_configured"
    assert "NOVELAI_TOKEN" in str(caught.value)


@pytest.mark.asyncio
async def test_status_reports_token_readiness_without_calling_upstream(
    tmp_path: Path,
) -> None:
    novelai_service = SimpleNamespace(
        token_readiness=lambda: token_readiness("${NOVELAI_TOKEN}"),
        generate=AsyncMock(),
    )
    handlers = _handlers(tmp_path=tmp_path, novelai_service=novelai_service)

    payload = await handlers.status({})

    assert payload["configured"] is False
    assert payload["reason"] == "placeholder"
    novelai_service.generate.assert_not_awaited()
