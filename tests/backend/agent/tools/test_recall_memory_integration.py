import json
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import agent.tools.recall_memory as recall_memory_module
import pytest
from agent.tools.recall_memory import RecallMemoryTool
from core.memory.engine import (
    EvidenceRef,
    MemoryQueryResult,
    MemoryRecord,
    MemoryToolSpec,
)


class _CaptureMemory:
    request = None

    async def query(self, request):
        self.request = request
        return MemoryQueryResult()


@pytest.mark.asyncio
async def test_recall_memory_passes_current_timestamp_to_engine() -> None:
    memory = _CaptureMemory()
    tool = RecallMemoryTool(
        cast(Any, memory),
        MemoryToolSpec(description="", parameters={"type": "object", "properties": {}}),
    )
    ts = datetime(2026, 4, 4, 22, 0, 0)

    _ = await tool.execute(
        query="memory", current_timestamp=ts.isoformat(), role_id="mira"
    )

    assert memory.request.timestamp == ts


@pytest.mark.asyncio
async def test_recall_memory_passes_memory_domain_to_engine() -> None:
    memory = _CaptureMemory()
    tool = RecallMemoryTool(
        cast(Any, memory),
        MemoryToolSpec(description="", parameters={"type": "object", "properties": {}}),
    )

    _ = await tool.execute(query="memory", memory_domain="role_self", role_id="mira")

    assert memory.request.filters.domains == ("role_self",)


def test_parse_time_filter_supports_presets_and_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tz = ZoneInfo("Asia/Shanghai")
    monkeypatch.setattr(
        recall_memory_module,
        "_now_local",
        lambda: datetime(2026, 4, 25, 15, 30, tzinfo=tz),
    )

    today = recall_memory_module._parse_time_filter("today")
    assert today is not None
    assert today[0] == datetime(2026, 4, 25, 0, 0, tzinfo=tz)
    assert today[1] == datetime(2026, 4, 26, 0, 0, tzinfo=tz)

    recent = recall_memory_module._parse_time_filter("recent_3d")
    assert recent is not None
    assert recent[0] == datetime(2026, 4, 22, 15, 30, tzinfo=tz)
    assert recent[1] == datetime(2026, 4, 25, 15, 30, tzinfo=tz)

    one_day = recall_memory_module._parse_time_filter("2026-04-20")
    assert one_day is not None
    assert one_day[0] == datetime(2026, 4, 20, 0, 0, tzinfo=tz)
    assert one_day[1] == datetime(2026, 4, 21, 0, 0, tzinfo=tz)

    date_range = recall_memory_module._parse_time_filter("2026-04-20~2026-04-25")
    assert date_range is not None
    assert date_range[0] == datetime(2026, 4, 20, 0, 0, tzinfo=tz)
    assert date_range[1] == datetime(2026, 4, 26, 0, 0, tzinfo=tz)


def test_recall_memory_response_preserves_activation_metadata() -> None:
    payload = json.loads(
        recall_memory_module._render_records(
            [
                MemoryRecord(
                    id="mem:1",
                    kind="event",
                    summary="用户提到 Falcons 比赛",
                    score=0.704,
                    engine_kind="default_memory",
                    evidence=[EvidenceRef(refs=["msg:1"], source_ref="msg:1")],
                    signals={
                        "cosine": 0.81,
                        "lambda_before": 0.2,
                        "lambda_after": 0.9,
                        "activation": 0.9,
                        "activated": True,
                    },
                )
            ],
            trace={},
        )
    )

    item = payload["items"][0]
    signals = item["signals"]
    assert signals["cosine"] == 0.81
    assert signals["lambda_before"] == 0.2
    assert signals["lambda_after"] == 0.9
    assert signals["activation"] == 0.9
    assert signals["activated"] is True
