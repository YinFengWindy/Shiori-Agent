from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from core.roles import RoleStore
from desktop_bridge.role_difference_service import (
    DEFAULT_ROLE_DIFFERENCES,
    RoleDifferenceGenerationService,
    _stable_seed,
)


def _write_generated_image(path: Path) -> None:
    image = Image.new("RGB", (20, 20), "white")
    for x in range(6, 14):
        for y in range(4, 17):
            image.putpixel((x, y), (210, 80, 110))
    image.save(path)


class FakeNovelAI:
    def __init__(self, output_dir: Path, *, fail_at: int | None = None) -> None:
        self.output_dir = output_dir
        self.fail_at = fail_at
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if self.fail_at == len(self.requests):
            raise ValueError("upstream generation failed")
        output = self.output_dir / f"generated-{len(self.requests)}.png"
        _write_generated_image(output)
        return SimpleNamespace(output_paths=[str(output)])


def _create_role(tmp_path: Path) -> tuple[RoleStore, str, Path]:
    base = tmp_path / "base.png"
    _write_generated_image(base)
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
        illustration_sources=[base],
    )
    return store, role.id, tmp_path / "generated"


@pytest.mark.asyncio
async def test_generates_all_differences_from_one_base_and_persists_one_category(
    tmp_path: Path,
) -> None:
    store, role_id, output_dir = _create_role(tmp_path)
    output_dir.mkdir()
    novelai = FakeNovelAI(output_dir)
    service = RoleDifferenceGenerationService(
        role_store=store,
        novelai_service=novelai,
        workspace=tmp_path,
    )
    events = []
    base_asset = store.get_role(role_id).illustrations[0]

    result = await service.generate(
        role_id=role_id,
        base_asset=base_asset,
        emit_progress=events.append,
    )

    role = result["role"]
    generated_category = role.asset_categories[-1]
    assert generated_category.name == "AI 差分"
    assert len(role.illustrations) == 6
    assert all(
        role.asset_category_bindings[path] == generated_category.id
        for path in role.illustrations[-5:]
    )
    assert [request.mode for request in novelai.requests] == ["img2img"] * 5
    assert {request.base_image_path for request in novelai.requests} == {
        str(store.resolve_role_asset_path(role_id, base_asset))
    }
    assert [request.seed for request in novelai.requests] == [
        _stable_seed(
            _file_hash(store.resolve_role_asset_path(role_id, base_asset)),
            difference_id,
        )
        for difference_id, _prompt in DEFAULT_ROLE_DIFFERENCES
    ]
    assert events[0]["phase"] == "started"
    assert events[-1]["phase"] == "finished"
    assert [event["phase"] for event in events[1:-1]].count("completed") == 5


@pytest.mark.asyncio
async def test_generation_failure_does_not_persist_partial_category(tmp_path: Path) -> None:
    store, role_id, output_dir = _create_role(tmp_path)
    output_dir.mkdir()
    novelai = FakeNovelAI(output_dir, fail_at=3)
    service = RoleDifferenceGenerationService(
        role_store=store,
        novelai_service=novelai,
        workspace=tmp_path,
    )
    events = []
    role_before = store.get_role(role_id)

    with pytest.raises(ValueError, match="upstream generation failed"):
        await service.generate(
            role_id=role_id,
            base_asset=role_before.illustrations[0],
            emit_progress=events.append,
        )

    role_after = store.get_role(role_id)
    assert role_after.asset_categories == role_before.asset_categories
    assert role_after.illustrations == role_before.illustrations
    assert events[-1]["phase"] == "failed"
    assert events[-1]["stages"][2]["status"] == "failed"


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
