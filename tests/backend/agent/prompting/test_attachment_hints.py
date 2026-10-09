"""Only envelope-owned attachment instructions can be removed from a request."""

from copy import deepcopy
import json

import pytest

from agent.context import MessageEnvelopeBuilder
from agent.prompting.attachment_hints import (
    ATTACHMENT_TOOL_HINTS_KEY,
    prepare_attachment_hints,
    without_attachment_tool_hints,
)


@pytest.mark.parametrize("tool_name", ["read_file", "read_attachment"])
@pytest.mark.parametrize("with_attachment", [False, True])
@pytest.mark.parametrize("multimodal", [False, True])
def test_only_generated_lines_are_removed_even_when_user_quotes_the_same_hint(
    tmp_path, tool_name, with_attachment, multimodal
):
    attachment = tmp_path / "notes.txt"
    attachment.write_text("notes", encoding="utf-8")
    hint = f"- 如需读取内容，请调用 {tool_name}(path={json.dumps(str(attachment), ensure_ascii=False)})"
    user_text = "Explain this quoted snippet:\n[附加文件]\n" + hint
    media = [str(attachment)] if with_attachment else []
    if multimodal:
        media.append("https://example.test/image.png")
    messages = MessageEnvelopeBuilder(multimodal=multimodal).build(
        history=[{"role": "user", "content": user_text}],
        current_message=user_text,
        system_prompt="system",
        context_frame="",
        channel="qq",
        message_timestamp=None,
        media=media,
        text_attachment_tool=tool_name,
    )
    original = deepcopy(messages)
    prepare_attachment_hints(messages, tools_enabled=False)
    assert messages[1] == original[1]
    content = messages[-1]["content"]
    text = content[-1]["text"] if isinstance(content, list) else content
    assert user_text in text
    assert text.count(hint) == 1
    assert ATTACHMENT_TOOL_HINTS_KEY not in messages[-1]
    if with_attachment:
        assert f"- 文件路径: {attachment}" in text
        assert ATTACHMENT_TOOL_HINTS_KEY in original[-1]
    if isinstance(content, list):
        assert content[:-1] == original[-1]["content"][:-1]
    # Already-cleaned content has no authority to delete the quoted line again.
    assert without_attachment_tool_hints(messages[-1]) == messages[-1]


def test_textless_user_parts_without_provenance_are_unchanged():
    message = {
        "role": "user",
        "content": [{"type": "text"}, {"type": "image_url", "image_url": {"url": "x"}}],
    }
    assert without_attachment_tool_hints(message) is message
