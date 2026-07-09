from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations.novelai.models import GenerateImageResult, GeneratedImageRecord
from core.integrations.novelai.store import NovelAIStore
from core.roles import RoleAggregateService, RoleStore
from desktop_bridge.image_service import DesktopImageService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_desktop_image_service_generates_with_role_session_key(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
    )
    _ = role_service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    novelai_store = NovelAIStore(tmp_path)
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
    service = DesktopImageService(
        role_service=role_service,
        novelai_service=novelai_service,  # type: ignore[arg-type]
        novelai_store=novelai_store,
    )

    payload = await service.generate(
        {
            "role_id": "mira",
            "prompt": "moonlight portrait",
            "mode": "txt2img",
        }
    )

    assert payload["record_id"] == "rec-1"
    request = novelai_service.generate.await_args.args[0]
    assert request.role_id == "mira"
    assert request.session_key == "role:mira"


def test_desktop_image_service_history_filters_by_role(tmp_path: Path):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
    )
    novelai_store = NovelAIStore(tmp_path)
    output_path = tmp_path / "private_runtime" / "novelai" / "outputs" / "out.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"png")
    novelai_store.append_record(
        GeneratedImageRecord(
            id="rec-1",
            created_at="2026-06-30T10:00:00+00:00",
            mode="txt2img",
            role_id="mira",
            session_key="role:mira",
            prompt="for mira",
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
    novelai_store.append_record(
        GeneratedImageRecord(
            id="rec-2",
            created_at="2026-06-30T11:00:00+00:00",
            mode="txt2img",
            role_id="atlas",
            session_key="role:atlas",
            prompt="for atlas",
            negative_prompt="",
            model="nai-diffusion-4-5-full",
            sampler="k_euler",
            steps=28,
            seed=2,
            width=1024,
            height=1024,
            base_image_path="",
            output_paths=[str(output_path)],
            wrote_back_to_role=False,
        )
    )
    service = DesktopImageService(
        role_service=role_service,
        novelai_service=None,
        novelai_store=novelai_store,
    )

    records = service.history({"role_id": "mira", "limit": 5})

    assert [record["id"] for record in records] == ["rec-1"]
