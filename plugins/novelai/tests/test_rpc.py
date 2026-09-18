from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.novelai.backend.models import GenerateImageResult, GeneratedImageRecord
from plugins.novelai.backend.prompt_tags import PromptTagStore
from plugins.novelai.backend.rpc import NovelAIRpcHandlers
from plugins.novelai.backend.store import NovelAIStore
from session.manager import SessionManager


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
        novelai_store=novelai_store or NovelAIStore(tmp_path),
        prompt_tag_store=prompt_tag_store or PromptTagStore(tmp_path),
        session_manager=session_manager or SessionManager(tmp_path),
        relationship_runtime=None,
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
    store = NovelAIStore(tmp_path)
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


def _persist_message(manager: SessionManager, old_path: str) -> tuple[str, str]:
    session = manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "scene",
        media=[str(Path(old_path).with_name("before.png")), old_path],
    )
    manager.save(session)
    return session.key, str(session.messages[-1]["id"])


def _write_generation_source(store: NovelAIStore, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"old")
    (output_path.parent / "request.json").write_text(
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
    store._records_path.write_text(
        json.dumps(
            {
                "id": "source-record",
                "created_at": "2026-07-22T08:00:00+00:00",
                "role_id": "mira",
                "session_key": "role:mira",
                "mode": "txt2img",
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "model": "nai-diffusion-4-5-curated",
                "sampler": "k_euler_ancestral",
                "steps": 28,
                "seed": None,
                "width": 1024,
                "height": 1024,
                "base_image_path": "",
                "output_paths": [str(output_path)],
                "wrote_back_to_role": False,
                "role_asset_paths": [],
            }
        ),
        encoding="utf-8",
    )


def _result(new_path: Path) -> GenerateImageResult:
    return GenerateImageResult(
        record_id="new-record",
        created_at="2026-07-22T08:01:00+00:00",
        mode="txt2img",
        model="nai-diffusion-4-5-curated",
        seed=101,
        width=1024,
        height=1024,
        output_paths=[str(new_path)],
        request_path=str(new_path.parent / "request.json"),
        meta_path=str(new_path.parent / "meta.json"),
    )


@pytest.mark.asyncio
async def test_regenerate_message_media_replaces_only_the_selected_slot(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    old_path = store._outputs_root / "2026-07-22" / "source-record" / "output-1.png"
    new_path = tmp_path / "new.png"
    new_path.write_bytes(b"new image")
    _write_generation_source(store, old_path)
    session_key, message_id = _persist_message(manager, str(old_path))
    novelai_service = AsyncMock()
    novelai_service.regenerate.return_value = _result(new_path)
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=manager,
        novelai_service=novelai_service,
        novelai_store=store,
    )

    payload = await handlers.regenerate_message_media(
        {"session_key": session_key, "message_id": message_id, "media_index": 1}
    )

    assert payload["result"]["record_id"] == "new-record"
    assert payload["session"]["key"] == session_key
    assert payload["message"]["id"] == message_id
    from session.media_assets import original_media_path

    copied_path = payload["message"]["media"][1]
    assert payload["message"]["media"][0] == str(old_path.with_name("before.png"))
    assert copied_path != str(new_path)
    assert Path(copied_path).read_bytes() == b"new image"
    assert original_media_path(tmp_path, copied_path) == str(new_path)
    new_path.unlink()
    manager.invalidate(session_key)
    assert manager.get_or_create(session_key).messages[-1]["media"][1] == copied_path


@pytest.mark.asyncio
async def test_regenerate_message_media_failure_preserves_old_media(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    old_path = store._outputs_root / "2026-07-22" / "source-record" / "output-1.png"
    _write_generation_source(store, old_path)
    session_key, message_id = _persist_message(manager, str(old_path))
    novelai_service = AsyncMock()
    novelai_service.regenerate.side_effect = RuntimeError("generation failed")
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=manager,
        novelai_service=novelai_service,
        novelai_store=store,
    )

    with pytest.raises(RuntimeError, match="generation failed"):
        await handlers.regenerate_message_media(
            {"session_key": session_key, "message_id": message_id, "media_index": 1}
        )

    from session.media_assets import original_media_path

    current = manager.get_or_create(session_key).messages[-1]["media"][1]
    assert original_media_path(tmp_path, current) == str(old_path)
    assert Path(current).read_bytes() == b"old"


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_concurrent_same_slot(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    old_path = store._outputs_root / "2026-07-22" / "source-record" / "output-1.png"
    _write_generation_source(store, old_path)
    session_key, message_id = _persist_message(manager, str(old_path))
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_regenerate(*_args, **_kwargs):
        started.set()
        await release.wait()
        return _result(tmp_path / "new.png")

    novelai_service = AsyncMock()
    novelai_service.regenerate.side_effect = delayed_regenerate
    handlers = _handlers(
        tmp_path=tmp_path,
        session_manager=manager,
        novelai_service=novelai_service,
        novelai_store=store,
    )
    payload = {"session_key": session_key, "message_id": message_id, "media_index": 1}
    first = asyncio.create_task(handlers.regenerate_message_media(payload))
    await started.wait()

    with pytest.raises(ValueError, match="正在重新生成"):
        await handlers.regenerate_message_media(payload)

    release.set()
    await first


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_non_novelai_image(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    session_key, message_id = _persist_message(manager, str(tmp_path / "plain.png"))
    handlers = _handlers(tmp_path=tmp_path, session_manager=manager)

    with pytest.raises(ValueError, match="不是 NovelAI"):
        await handlers.regenerate_message_media(
            {"session_key": session_key, "message_id": message_id, "media_index": 1}
        )


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
