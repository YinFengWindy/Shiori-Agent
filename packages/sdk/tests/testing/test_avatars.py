"""Avatar fake errors remain observable after completed task references are released."""

import asyncio

import pytest

from shiori_sdk.testing.avatars import FakeAvatars


async def test_drain_reports_an_already_completed_fetch_failure_once():
    avatars = FakeAvatars()
    failure = ValueError("unconfigured avatar response")

    async def fetch() -> bytes:
        await asyncio.sleep(0)
        raise failure

    task = avatars.refresh("sender", "example", "1", fetch)
    await asyncio.wait([task])
    assert avatars.tasks == set()
    with pytest.raises(ExceptionGroup) as reported:
        await avatars.drain()
    assert reported.value.exceptions == (failure,)
    assert avatars._errors == []
    await avatars.drain()
    await avatars.aclose()
