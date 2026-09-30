"""avatars.py 行为：refresh 只在到期时后台获取、失败只记警告，并随作用域释放。"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from agent.plugin_host.avatars import AvatarsCapability
from agent.plugin_host.effects import EffectScope
from core.channel_avatars import ChannelAvatarStore


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (300, 300), "pink").save(output, format="PNG")
    return output.getvalue()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def _capability(tmp_path: Path) -> tuple[AvatarsCapability, ChannelAvatarStore, _Clock]:
    clock = _Clock()
    store = ChannelAvatarStore(tmp_path, clock=clock)
    return AvatarsCapability(store, EffectScope("qq"), "qq"), store, clock


async def test_refresh_fetches_in_the_background_only_when_due(tmp_path: Path) -> None:
    avatars, store, clock = _capability(tmp_path)
    fetched: list[str] = []

    async def fetch() -> bytes:
        fetched.append("42")
        return _png()

    task = avatars.refresh("sender", "qq", "42", fetch)
    assert task is not None
    await task
    assert avatars.refresh("sender", "qq", "42", fetch) is None
    clock.now += timedelta(days=7)
    again = avatars.refresh("sender", "qq", "42", fetch)
    assert again is not None
    await again

    assert fetched == ["42", "42"]
    assert store.index().sender("qq", "42") is not None


async def test_fetch_answering_none_records_no_avatar(tmp_path: Path) -> None:
    avatars, store, _ = _capability(tmp_path)

    async def fetch() -> None:
        return None

    task = avatars.refresh("chat", "qq", "gqq:5", fetch)
    assert task is not None
    await task

    assert store.index().chat("qq", "gqq:5") is None
    assert avatars.refresh("chat", "qq", "gqq:5", fetch) is None


@pytest.mark.parametrize(
    "outcome", [ConnectionError("platform down"), b"<html>"], ids=["fetch", "save"]
)
async def test_failure_logs_a_warning_and_waits_until_due(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, outcome: object
) -> None:
    avatars, store, clock = _capability(tmp_path)

    async def fetch() -> bytes:
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, bytes)
        return outcome

    task = avatars.refresh("sender", "qq", "42", fetch)
    assert task is not None
    with caplog.at_level(logging.WARNING):
        await task

    assert "头像获取失败" in caplog.text
    assert store.index().sender("qq", "42") is None
    assert avatars.refresh("sender", "qq", "42", fetch) is None
    clock.now += timedelta(days=7)
    retry = avatars.refresh("sender", "qq", "42", fetch)
    assert retry is not None
    await retry


def test_unknown_kind_is_refused(tmp_path: Path) -> None:
    avatars, _, _ = _capability(tmp_path)

    async def fetch() -> None:
        return None

    with pytest.raises(ValueError):
        _ = avatars.refresh("member", "qq", "42", fetch)


async def test_released_scope_cancels_pending_fetches_and_refuses_calls(
    tmp_path: Path,
) -> None:
    effects = EffectScope("qq")
    store = ChannelAvatarStore(tmp_path)
    avatars = AvatarsCapability(store, effects, "qq")
    started = asyncio.Event()

    async def fetch() -> bytes:
        started.set()
        await asyncio.sleep(3600)
        return _png()

    task = avatars.refresh("sender", "qq", "42", fetch)
    assert task is not None
    await started.wait()

    assert await effects.dispose_all() == []

    assert task.done()
    assert store.index().sender("qq", "42") is None
    with pytest.raises(RuntimeError):
        _ = avatars.refresh("sender", "qq", "7", fetch)
