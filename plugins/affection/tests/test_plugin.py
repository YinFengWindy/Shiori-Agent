"""The affection plugin's setup: its UI's RPC and the sidebar refresh event."""

from __future__ import annotations

from pathlib import Path

import pytest
from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.affection_host import AFFECTION_HOST
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.affection.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]

_SNAPSHOT_REPLY = (
    '{"role_self_view":"我会留意你有没有来找我。",'
    '"relation_tags":["亲近"],'
    '"relation_state":{"dependence":0.5,"security":0.4,'
    '"initiative_desire":0.7,"neglect_sensitivity":0.8},'
    '"behavior_profile":{"loneliness_growth_base":1.5,'
    '"loneliness_growth_when_unanswered":2.2,"trigger_threshold":60,'
    '"post_trigger_cooldown_minutes":120,"night_suppression":0.4}}'
)


@pytest.fixture
async def context(tmp_path: Path, host):
    fake = FakeServiceContext("affection", tmp_path, package_dir=PACKAGE_DIR)
    fake.serve(AFFECTION_HOST, host)
    await setup(fake)
    try:
        yield fake
    finally:
        await fake.aclose()


async def test_chat_status_rpc_answers_for_a_known_role_and_rejects_others(context):
    chat_status = context.fake_rpc.handlers["chat_status"]

    assert (await chat_status({"role_id": " mira "}))["role_id"] == "mira"
    with pytest.raises(ValueError, match="role not found"):
        await chat_status({"role_id": "ghost"})


async def test_a_snapshot_refresh_tells_the_sidebar_of_that_role(context, host):
    host.completion = _SNAPSHOT_REPLY
    session = host.get_session(host.role_session_key("mira"))
    session.messages = [{"role": "user", "content": "你好"}]
    runtime = context.kernel.get(AFFECTION)

    await runtime.refresh_snapshot_after_consolidation(session.key)

    assert context.fake_rpc.events == [("chat_status.changed", {"role_id": "mira"})]
    status = await context.fake_rpc.handlers["chat_status"]({"role_id": "mira"})
    assert status["relation_tags"] == ["亲近"]
