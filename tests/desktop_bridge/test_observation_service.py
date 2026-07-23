from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from desktop_bridge.observation_service import DesktopObservationService


@pytest.mark.asyncio
async def test_service_keeps_model_and_memory_operations_separate() -> None:
    service = DesktopObservationService(
        roles=SimpleNamespace(),
        provider=SimpleNamespace(),
        model="vision-model",
        memory=SimpleNamespace(),
    )
    service._model_adapter.analyze = AsyncMock(return_value={"frame_id": "frame-1"})
    service._memory_writer.remember = AsyncMock(return_value={"item_id": "event-1"})

    assert await service.analyze({"frame_id": "frame-1"}) == {"frame_id": "frame-1"}
    assert await service.remember({"summary": "共同经历"}) == {"item_id": "event-1"}
    service._model_adapter.analyze.assert_awaited_once()
    service._memory_writer.remember.assert_awaited_once()
