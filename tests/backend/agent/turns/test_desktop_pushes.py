import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.turns.desktop_pushes import DesktopPushDrafts, current_desktop_pushes


async def test_closed_and_inherited_scopes_cannot_capture_later_background_work():
    drafts = DesktopPushDrafts("role:mira")
    effect = AsyncMock()
    started = asyncio.Event()
    resume = asyncio.Event()

    async def detached():
        started.set()
        await resume.wait()
        return current_desktop_pushes("role:mira")

    with drafts.collect():
        task = asyncio.create_task(detached())
        await started.wait()
        assert current_desktop_pushes("role:mira") is drafts
        assert current_desktop_pushes("role:other") is None
        drafts.append({"content": "queued"}, owner=effect, after_commit=effect)
        drafts.append({"content": "another"}, owner=effect, after_commit=effect)
        effect.assert_not_awaited()
    resume.set()
    assert await task is None
    assert current_desktop_pushes("role:mira") is None
    with pytest.raises(RuntimeError, match="已结束"):
        drafts.append({"content": "late"}, owner=effect, after_commit=effect)
    await drafts.committed()
    await drafts.committed()
    effect.assert_awaited_once()
