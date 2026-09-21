"""MCP response conversion preserves original bytes and existing non-image text."""

import pytest

from agent.mcp.result import decode_tool_result
from agent.tools.base import ToolResult


def test_text_and_resource_content_remain_text():
    blocks = [
        {"type": "text", "text": "hello"},
        {"type": "resource_link", "uri": "file:///example"},
    ]
    assert decode_tool_result(
        "test", "read", {"result": {"content": blocks}}
    ) == "hello\n" + str(blocks[1])


@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "image/gif", "image/webp"])
def test_inline_images_keep_mime_and_original_base64(mime):
    result = decode_tool_result(
        "test",
        "read",
        {
            "result": {
                "content": [{"type": "image", "mimeType": mime, "data": "aGVsbG8="}]
            }
        },
    )
    assert isinstance(result, ToolResult)
    assert result.text == ""
    assert (
        result.content_blocks[0]["image_url"]["url"] == f"data:{mime};base64,aGVsbG8="
    )


@pytest.mark.parametrize(
    "mime,data",
    [("text/html", "aGVsbG8="), ("image/png", "!not-base64"), ("image/png", "")],
)
def test_invalid_image_fails_explicitly(mime, data):
    with pytest.raises(ValueError):
        decode_tool_result(
            "test",
            "read",
            {
                "result": {
                    "content": [{"type": "image", "mimeType": mime, "data": data}]
                }
            },
        )
