from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations.novelai.models import GenerateImageResult
from core.integrations.novelai.store import NovelAIStore
from desktop_bridge.image_service import DesktopImageService
from session.manager import SessionManager


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


def _service(
    manager: SessionManager,
    store: NovelAIStore,
    novelai_service: AsyncMock,
) -> DesktopImageService:
    return DesktopImageService(
        role_service=SimpleNamespace(sessions=manager),
        session_manager=manager,
        novelai_service=novelai_service,
        novelai_store=store,
    )


@pytest.mark.asyncio
async def test_regenerate_message_media_replaces_only_the_selected_slot(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    old_path = store._outputs_root / "2026-07-22" / "source-record" / "output-1.png"
    new_path = tmp_path / "new.png"
    _write_generation_source(store, old_path)
    session_key, message_id = _persist_message(manager, str(old_path))
    novelai_service = AsyncMock()
    novelai_service.regenerate.return_value = _result(new_path)
    service = _service(manager, store, novelai_service)

    generation, session = await service.regenerate_message_media(
        {
            "session_key": session_key,
            "message_id": message_id,
            "media_index": 1,
        }
    )

    assert generation["record_id"] == "new-record"
    assert session.messages[-1]["id"] == message_id
    assert session.messages[-1]["media"] == [
        str(old_path.with_name("before.png")),
        str(new_path),
    ]
    manager.invalidate(session_key)
    assert manager.get_or_create(session_key).messages[-1]["media"][1] == str(new_path)


@pytest.mark.asyncio
async def test_regenerate_message_media_failure_preserves_old_media(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    old_path = store._outputs_root / "2026-07-22" / "source-record" / "output-1.png"
    _write_generation_source(store, old_path)
    session_key, message_id = _persist_message(manager, str(old_path))
    novelai_service = AsyncMock()
    novelai_service.regenerate.side_effect = RuntimeError("generation failed")
    service = _service(manager, store, novelai_service)

    with pytest.raises(RuntimeError, match="generation failed"):
        await service.regenerate_message_media(
            {
                "session_key": session_key,
                "message_id": message_id,
                "media_index": 1,
            }
        )

    assert manager.get_or_create(session_key).messages[-1]["media"][1] == str(old_path)


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_concurrent_same_slot(tmp_path: Path) -> None:
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
    service = _service(manager, store, novelai_service)
    payload = {
        "session_key": session_key,
        "message_id": message_id,
        "media_index": 1,
    }
    first = asyncio.create_task(service.regenerate_message_media(payload))
    await started.wait()

    with pytest.raises(ValueError, match="正在重新生成"):
        await service.regenerate_message_media(payload)

    release.set()
    await first


@pytest.mark.asyncio
async def test_regenerate_message_media_rejects_non_novelai_image(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    store = NovelAIStore(tmp_path)
    session_key, message_id = _persist_message(manager, str(tmp_path / "plain.png"))
    service = _service(manager, store, AsyncMock())

    with pytest.raises(ValueError, match="不是 NovelAI"):
        await service.regenerate_message_media(
            {
                "session_key": session_key,
                "message_id": message_id,
                "media_index": 1,
            }
        )
