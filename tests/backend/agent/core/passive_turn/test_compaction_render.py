"""Candidate rendering refreshes history-derived inputs but freezes the live user input."""

from datetime import datetime
from unittest.mock import AsyncMock

from agent.core.passive_turn.compaction_render import CompactionRenderer
from agent.lifecycle.types import PromptRenderInput, PromptRenderResult
from agent.tools.registry import ToolRegistry
from conversation.context_scope import turn_context_view
from conversation.service import network_thread_id
from session.manager import SessionManager


async def test_render_refreshes_member_sources_without_replacing_current_attachments(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    thread = network_thread_id("mira", "qq", "group")
    for sender in ["old", "retained"]:
        session.add_message(
            "user",
            sender,
            thread_id=thread,
            metadata={"message_source": {"sender_id": sender, "group_name": "group"}},
        )
        session.add_message("assistant", "done", thread_id=thread)
    manager.save(session)
    view = turn_context_view(tmp_path, "mira", thread)
    prepared = await manager.prepare_window(session.key, view, keep_turns=1)
    assert prepared is not None
    current = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,original"},
            },
            {"type": "text", "text": "unaltered input"},
        ],
    }
    request = PromptRenderInput(
        session_key=session.key,
        channel="qq",
        chat_id="group",
        content="unaltered input",
        media=["current.png"],
        timestamp=datetime.now(),
        history=[],
        skill_names=None,
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
    )
    render = AsyncMock(
        return_value=PromptRenderResult(
            messages=[
                {"role": "system", "content": "new context"},
                {"role": "user", "content": "plugin replacement"},
            ]
        )
    )
    renderer = CompactionRenderer(
        manager,
        view,
        len(session.messages),
        request,
        current,
        render,
        ToolRegistry(),
        False,
        set(),
        False,
        lambda: [],
    )
    result = await renderer.render(prepared, "working task", [])
    assert result[-1] == current
    assert result[1]["content"].startswith("[working_state]")
    called = render.await_args.args[0]
    assert [source.sender_id for source in called.window_sources] == ["retained"]
    assert len(called.history) == 2
    assert "retained" in called.history[0]["content"]


async def test_minimal_render_drops_disabled_read_file_instruction(tmp_path):
    from agent.context import MessageEnvelopeBuilder

    attachment = tmp_path / "notes.txt"
    attachment.write_text("notes", encoding="utf-8")
    text = MessageEnvelopeBuilder()._append_text_attachment_refs(
        "look", [str(attachment)]
    )
    assert "read_file(" in text
    current = {"role": "user", "content": text}
    request = PromptRenderInput(
        session_key="cli:minimal",
        channel="cli",
        chat_id="minimal",
        content="look",
        media=[str(attachment)],
        timestamp=datetime.now(),
        history=[],
        skill_names=None,
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
    )
    render = AsyncMock(
        return_value=PromptRenderResult(
            messages=[
                {"role": "system", "content": "constraints"},
                {"role": "user", "content": text},
            ]
        )
    )
    renderer = CompactionRenderer(
        SessionManager(tmp_path),
        None,
        0,
        request,
        current,
        render,
        ToolRegistry(),
        False,
        set(),
        False,
        lambda: [],
    )
    result = await renderer.render_minimal("")
    assert "read_file(" not in result[-1]["content"]
    assert str(attachment) in result[-1]["content"] and "look" in result[-1]["content"]
    assert "read_file(" in current["content"]
