"""Independent plugin setup and configuration contracts."""

import pytest
from shiori_sdk.lifecycle import ResponseMetadata, AfterReasoningCtx
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.roles import FakeCategory
from plugins.meme.backend.plugin import setup


@pytest.mark.parametrize("sendable", [True, False])
async def test_setup_resolves_injected_role_assets_and_emoji(tmp_path, sendable):
    context = FakeServiceContext("meme", tmp_path)
    role = context.roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    source = tmp_path / "reaction.png"
    source.write_bytes(b"image")
    asset = context.roles.add_illustration("mira", source)
    role.asset_categories = [FakeCategory("happy", "开心", sendable)]
    role.asset_category_bindings[asset] = "happy"
    context.sessions.get_or_create("role:mira").metadata["role_id"] = "mira"
    (tmp_path / "common_emojis.json").write_text(
        '[{"name":"heart","value":"♥"}]', encoding="utf-8"
    )
    await setup(context.as_capability())
    assert len(context.lifecycle.modules["prompt_render"]) == 1
    event = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="desktop",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="test"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="好 <meme:happy> <emoji:heart> <emoji:unknown>",
    )
    await context.events.emit(event)
    assert event.reply == "好  ♥"
    assert event.media == ([str(context.roles.asset_path(asset))] if sendable else [])
    lifecycle = context.lifecycle
    await context.aclose()
    assert not lifecycle.modules
