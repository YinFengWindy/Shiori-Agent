"""Independent plugin setup, prompt contribution and reply protocol contracts."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from shiori_sdk.lifecycle import ResponseMetadata, AfterReasoningCtx, PromptRenderCtx
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.roles import FakeCategory
from plugins.meme.backend.plugin import setup


def _reply(reply: str, *, session_key: str = "role:mira") -> AfterReasoningCtx:
    return AfterReasoningCtx(
        session_key=session_key,
        channel="desktop",
        chat_id="desktop",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text=reply),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply=reply,
    )


def _prompt(*, role_id: str = "") -> PromptRenderCtx:
    return PromptRenderCtx(
        session_key="role:mira" if role_id else "telegram:1",
        channel="desktop",
        chat_id="1",
        content="你好",
        media=None,
        timestamp=datetime.now(timezone.utc),
        history=[],
        skill_names=[],
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
        session_metadata={"role_id": role_id} if role_id else {},
    )


def _write_library(workspace: Path) -> Path:
    """Seed the legacy ``memes`` layout at the path storage migration returns."""
    library = workspace / "plugin-data" / "meme" / "library"
    (library / "shy").mkdir(parents=True)
    image = library / "shy" / "001.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    (library / "manifest.json").write_text(
        json.dumps(
            {"categories": {"shy": {"desc": "害羞", "enabled": True}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return image


async def _setup_role(tmp_path: Path, *, sendable: bool = True):
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
    return context, asset


@pytest.mark.parametrize("sendable", [True, False])
async def test_setup_resolves_injected_role_assets_and_emoji(tmp_path, sendable):
    context, asset = await _setup_role(tmp_path, sendable=sendable)
    assert len(context.lifecycle.modules["prompt_render"]) == 1
    event = _reply("好 <meme:happy> <emoji:heart> <emoji:unknown>")
    await context.events.emit(event)
    assert event.reply == "好  ♥"
    assert event.media == ([str(context.roles.asset_path(asset))] if sendable else [])
    lifecycle = context.lifecycle
    await context.aclose()
    assert not lifecycle.modules


async def test_role_prompt_lists_sendable_categories_and_shared_emoji(tmp_path):
    context, _ = await _setup_role(tmp_path)
    ctx = _prompt(role_id="mira")
    [module] = context.lifecycle.modules["prompt_render"]

    await module.run(SimpleNamespace(slots={"prompt:ctx": ctx}))

    [section] = ctx.system_sections_bottom
    assert section.name == "memes"
    assert "<meme:分类ID>" in section.content
    assert "happy: 开心" in section.content
    assert "heart: ♥" in section.content
    await context.aclose()


async def test_library_prompt_and_reply_without_a_role(tmp_path):
    image = _write_library(tmp_path)
    context = FakeServiceContext("meme", tmp_path)
    await setup(context.as_capability())
    ctx = _prompt()
    [module] = context.lifecycle.modules["prompt_render"]

    await module.run(SimpleNamespace(slots={"prompt:ctx": ctx}))
    event = _reply("好的 <MEME:Shy> <meme:other>", session_key="telegram:1")
    await context.events.emit(event)

    assert "<meme:shy>" in ctx.system_sections_bottom[0].content
    assert event.reply == "好的"
    assert event.media == [str(image)]
    assert event.meme_tag == "shy"
    await context.aclose()


@pytest.mark.parametrize(
    "reply,tag", [("好的 <meme:>", None), ("好的 <meme:missing>", "missing")]
)
async def test_empty_or_unknown_meme_tag_is_stripped_without_media(
    tmp_path, reply, tag
):
    _write_library(tmp_path)
    context = FakeServiceContext("meme", tmp_path)
    await setup(context.as_capability())
    event = _reply(reply, session_key="telegram:1")

    await context.events.emit(event)

    assert event.reply == "好的"
    assert event.media == []
    assert event.meme_tag == tag
    await context.aclose()
