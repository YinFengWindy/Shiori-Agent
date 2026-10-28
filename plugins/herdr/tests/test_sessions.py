"""`sessions.list` reports local Herdr sessions and surfaces CLI failures."""

from pathlib import Path
import json
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
async def context(tmp_path):
    context = FakeServiceContext(
        "herdr",
        tmp_path,
        config={"executable": "custom-herdr", "session": "mine"},
        package_dir=PACKAGE_DIR,
    )
    await setup(context)
    yield context
    await context.aclose()


async def test_lists_every_session_with_its_running_state(context, monkeypatch):
    output = {
        "sessions": [
            {"name": "default", "running": True, "session_dir": "C:\\a b"},
            {"name": "shiori-smoke-816", "running": False, "session_dir": "C:\\c"},
        ]
    }
    command = AsyncMock(return_value=json.dumps(output))
    monkeypatch.setattr(HerdrCli, "command", command)

    assert context.fake_rpc.concurrency["sessions.list"] is Concurrency.READ_ONLY
    listed = await context.fake_rpc.handlers["sessions.list"]({})

    assert listed == {
        "sessions": [
            {"name": "default", "status": "running"},
            {"name": "shiori-smoke-816", "status": "stopped"},
        ]
    }
    # Not pinned to the configured session: listing must work while it is stopped.
    command.assert_awaited_once_with(["custom-herdr", "session", "list", "--json"])


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (AsyncMock(side_effect=FileNotFoundError("找不到可执行程序：herdr")), "找不到"),
        (AsyncMock(side_effect=CommandError("unknown subcommand")), "unknown"),
        (AsyncMock(return_value="name status\ndefault running"), "无法识别"),
    ],
)
async def test_unavailable_herdr_or_unreadable_output_fails_the_request(
    context, monkeypatch, command, message
):
    monkeypatch.setattr(HerdrCli, "command", command)
    with pytest.raises((FileNotFoundError, CommandError), match=message):
        await context.fake_rpc.handlers["sessions.list"]({})
