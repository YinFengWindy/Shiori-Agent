import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.turns.turn_pushes import TurnPushDrafts, current_turn_pushes


async def test_closed_and_inherited_scopes_cannot_capture_later_background_work():
    drafts = TurnPushDrafts("role:mira")
    effect = AsyncMock()
    started = asyncio.Event()
    resume = asyncio.Event()

    async def detached():
        started.set()
        await resume.wait()
        return current_turn_pushes("role:mira")

    with drafts.collect():
        task = asyncio.create_task(detached())
        await started.wait()
        assert current_turn_pushes("role:mira") is drafts
        assert current_turn_pushes("role:other") is None
        drafts.append({"content": "queued"}, owner=effect, after_commit=effect)
        drafts.append({"content": "another"}, owner=effect, after_commit=effect)
        effect.assert_not_awaited()
    resume.set()
    assert await task is None
    assert current_turn_pushes("role:mira") is None
    with pytest.raises(RuntimeError, match="回合已结束"):
        drafts.append({"content": "late"}, owner=effect, after_commit=effect)
    await drafts.committed()
    await drafts.committed()
    effect.assert_awaited_once()


async def test_abandoned_runs_every_record_and_raises_their_failures():
    drafts = TurnPushDrafts("role:mira")
    records = [AsyncMock(side_effect=OSError("disk")), AsyncMock()]
    with drafts.collect():
        for record in records:
            drafts.append({}, owner=record, if_abandoned=record)

    # No turn error to protect: the failure is the one raised.
    with pytest.raises(ExceptionGroup) as raised:
        await drafts.abandoned()

    assert [type(error) for error in raised.value.exceptions] == [OSError]
    for record in records:
        record.assert_awaited_once()
