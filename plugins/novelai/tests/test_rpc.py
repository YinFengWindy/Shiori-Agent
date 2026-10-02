from __future__ import annotations
from shiori_sdk.testing.memory import FakeMemoryStorage

import asyncio
import json
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
from shiori_sdk.testing.sessions import FakeSessions


def _handlers(
    *,
    tmp_path: Path,
    session_manager: FakeSessions | None = None,
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
        session_manager=session_manager or FakeSessions(),
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


_SESSION, _MESSAGE = "role:mira", "message-1"
_SLOT = {"session_key": _SESSION, "message_id": _MESSAGE, "media_index": 1}


def _regeneration_fixture(
    tmp_path: Path, *, novelai_image: bool = True
) -> tuple[NovelAIStore, FakeSessions, Path]:
    """Seed a session slot holding a host-owned copy of a NovelAI output.

    ``FakeSessions.provenance`` maps the copy back to the original output, the
    same way the host's ``original_media_path`` does for session-owned media.
    """
    sessions = FakeSessions()
    store = NovelAIStore(
        tmp_path,
        storage=FakeMemoryStorage(),
        original_media=sessions.original_media_path,
    )
    original = tmp_path / "outputs" / "source-record" / "output-1.png"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"old")
    (original.parent / "request.json").write_text(
        json.dumps(
            {
                "action": "generate",
                "input": "1girl, rain",
                "model": "nai-diffusion-4-5-curated",
                "parameters": {
                    "width": 1024,
                    "height": 1024,
                    "steps": 28,
                    "sampler": "k_euler_ancestral",
                    "negative_prompt": "blurry",
                },
            }
        ),
        encoding="utf-8",
    )
    if novelai_image:
        store.append_record(
            GeneratedImageRecord(
                id="source-record",
                created_at="2026-07-22T08:00:00+00:00",
                role_id="mira",
                session_key=_SESSION,
                mode="txt2img",
                prompt="1girl, rain",
                negative_prompt="blurry",
                model="nai-diffusion-4-5-curated",
                sampler="k_euler_ancestral",
                steps=28,
                seed=None,
                width=1024,
                height=1024,
                base_image_path="",
                output_paths=[str(original)],
                wrote_back_to_role=False,
            )
        )
    sessions.media[_SESSION, _MESSAGE, 0] = "session-copy/before.png"
    sessions.media[_SESSION, _MESSAGE, 1] = "session-copy/output-1.png"
    sessions.provenance["session-copy/output-1.png"] = str(original)
    sessions.replacement = {"session": {"key": _SESSION}, "message": {"id": _MESSAGE}}
    return store, sessions, original


def _regenerated(path: Path) -> GenerateImageResult:
    return GenerateImageResult(
        record_id="new-record",
        created_at="2026-07-22T08:01:00+00:00",
        mode="txt2img",
        model="nai-diffusion-4-5-curated",
        seed=101,
        width=1024,
        height=1024,
        output_paths=[str(path)],
        request_path=str(path.parent / "request.json"),
        meta_path=str(path.parent / "meta.json"),
    )


@pytest.mark.asyncio
async def test_regenerate_message_media_replaces_only_the_selected_slot(
    tmp_path: Path,
) -> None:
    store, sessions, original = _regeneration_fixture(tmp_path)
    service = SimpleNamespace(
        regenerate=AsyncMock(return_value=_regenerated(tmp_path / "new.png"))
    )
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=sessions,
        novelai_service=service,
        novelai_store=store,
    )

    payload = await handlers.regenerate_message_media(_SLOT)

    source = service.regenerate.await_args.args[0]
    assert source.output_path == str(original)
    assert service.regenerate.await_args.kwargs == {"session_key": _SESSION}
    assert sessions.media == {
        (_SESSION, _MESSAGE, 0): "session-copy/before.png",
        (_SESSION, _MESSAGE, 1): str(tmp_path / "new.png"),
    }
    assert payload["result"]["record_id"] == "new-record"
    assert payload["session"] == {"key": _SESSION}
    assert payload["message"] == {"id": _MESSAGE}


@pytest.mark.asyncio
async def test_regenerate_message_media_failure_preserves_old_media(
    tmp_path: Path,
) -> None:
    store, sessions, _ = _regeneration_fixture(tmp_path)
    service = SimpleNamespace(
        regenerate=AsyncMock(
            side_effect=[
                RuntimeError("generation failed"),
                _regenerated(tmp_path / "new.png"),
            ]
        )
    )
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=sessions,
        novelai_service=service,
        novelai_store=store,
    )

    with pytest.raises(RuntimeError, match="generation failed"):
        await handlers.regenerate_message_media(_SLOT)

    assert sessions.media[_SESSION, _MESSAGE, 1] == "session-copy/output-1.png"
    # The failed attempt must release its slot so a retry is accepted.
    await handlers.regenerate_message_media(_SLOT)
    assert sessions.media[_SESSION, _MESSAGE, 1] == str(tmp_path / "new.png")


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_concurrent_same_slot(
    tmp_path: Path,
) -> None:
    store, sessions, _ = _regeneration_fixture(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_regenerate(*_args, **_kwargs):
        started.set()
        await release.wait()
        return _regenerated(tmp_path / "new.png")

    service = SimpleNamespace(regenerate=AsyncMock(side_effect=delayed_regenerate))
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=sessions,
        novelai_service=service,
        novelai_store=store,
    )
    first = asyncio.create_task(handlers.regenerate_message_media(_SLOT))
    await started.wait()

    with pytest.raises(ValueError, match="正在重新生成"):
        await handlers.regenerate_message_media(_SLOT)

    release.set()
    await first
    assert service.regenerate.await_count == 1
    assert sessions.media[_SESSION, _MESSAGE, 1] == str(tmp_path / "new.png")


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_non_novelai_image(
    tmp_path: Path,
) -> None:
    store, sessions, _ = _regeneration_fixture(tmp_path, novelai_image=False)
    service = SimpleNamespace(regenerate=AsyncMock())
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=sessions,
        novelai_service=service,
        novelai_store=store,
    )

    with pytest.raises(ValueError, match="不是 NovelAI"):
        await handlers.regenerate_message_media(_SLOT)

    service.regenerate.assert_not_awaited()
    assert sessions.media[_SESSION, _MESSAGE, 1] == "session-copy/output-1.png"
