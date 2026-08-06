from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


def _write_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (20, 20), "white")
    for x in range(6, 14):
        for y in range(4, 17):
            image.putpixel((x, y), color)
    image.save(path)


class FakeNovelAI:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.index = 0

    async def generate(self, _request):
        self.index += 1
        output = self.output_dir / f"generated-{self.index}.png"
        _write_image(output, (210, 80, 110))
        return SimpleNamespace(output_paths=[str(output)])


@pytest.mark.asyncio
async def test_role_difference_rpc_publishes_progress_and_returns_updated_role(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.png"
    _write_image(base, (57, 120, 200))
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
        illustration_sources=[base],
    )
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        novelai_service=FakeNovelAI(generated_dir),
    )
    events: list[dict] = []
    service.add_event_listener(events.append)

    response = await service.handle(
        {
            "id": "difference-job-1",
            "method": "roles.differences.generate",
            "payload": {"role_id": role.id, "base_asset": role.illustrations[0]},
        },
        emit_event=lambda _payload: None,
    )

    assert response.error is None
    assert response.payload["role"]["asset_categories"][-1]["name"] == "AI 差分"
    assert [event["method"] for event in events].count(
        "roles.differences.progress"
    ) == 12
    assert events[-1]["payload"]["phase"] == "finished"
    session_config = session_manager.get_or_create("role:mira").metadata[
        "role_runtime_config"
    ]
    assert session_config["mood_catalog"] == ["平静", "开心", "惊讶", "生气", "悲伤"]
    assert set(session_config["mood_illustration_bindings"]) == set(
        session_config["mood_catalog"]
    )
    await service.aclose()
