"""The plugin contributes only opted-in presentation and unloads cleanly."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from plugins.natural_chat.backend.plugin import SEPARATOR, setup
from shiori_sdk.lifecycle import PromptRenderCtx
from shiori_sdk.testing.service_context import FakeServiceContext


@pytest.mark.parametrize(
    "enabled,supported", [(False, True), (True, False), (True, True)]
)
async def test_prompt_requires_role_choice_and_supported_turn(
    tmp_path, enabled, supported
):
    context = FakeServiceContext("natural_chat", tmp_path)
    context.roles.create_role(
        role_id="a", name="A", system_prompt="original personality"
    )
    context.roles.extensions.values["natural_chat"] = {"a": {"enabled": enabled}}
    await setup(context.as_capability())
    ctx = PromptRenderCtx(
        session_key="role:a",
        channel="desktop",
        chat_id="role:a",
        content="hi",
        media=None,
        timestamp=datetime.now(timezone.utc),
        history=[],
        skill_names=[],
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
        session_metadata={"role_id": "a"},
        supports_reply_sequence=supported,
    )
    [module] = context.lifecycle.modules["prompt_render"]
    await module.run(SimpleNamespace(slots={"prompt:ctx": ctx}))
    if enabled and supported:
        assert ctx.reply_sequence is not None
        assert ctx.reply_sequence.separator == SEPARATOR
        assert SEPARATOR in ctx.system_sections_bottom[0].content
    else:
        assert ctx.reply_sequence is None
        assert not ctx.system_sections_bottom
    assert context.roles.get_role("a").system_prompt == "original personality"
    assert "natural_chat" in context.roles.extensions.participants
    lifecycle = context.lifecycle
    await context.aclose()
    assert not lifecycle.modules
    assert not context.roles.extensions.participants
