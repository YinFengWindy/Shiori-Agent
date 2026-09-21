"""MCP response conversion preserves original bytes and existing non-image text."""

import pytest

from agent.mcp.result import decode_tool_result
from agent.tools.base import ToolResult


def test_structured_snapshot_identity_is_available_to_adapter_and_current_model():
    structured = {
        "pid": 42,
        "window_id": 81,
        "snapshot_id": "s00000001",
        "elements": [{"element_token": "s00000001:1", "label": "中文"}],
    }
    result = decode_tool_result(
        "cua",
        "get_window_state",
        {
            "result": {
                "content": [
                    {"type": "text", "text": "observed"},
                    {"type": "image", "mimeType": "image/png", "data": "aGVsbG8="},
                ],
                "structuredContent": structured,
            }
        },
    )
    assert isinstance(result, ToolResult)
    assert result.structured_content == structured
    assert '"element_token": "s00000001:1"' in result.text
    assert result.text.startswith("observed\n")
    assert "aGVsbG8=" not in result.text


def test_structured_only_result_is_not_discarded():
    result = decode_tool_result(
        "cua",
        "list_windows",
        {"result": {"structuredContent": {"windows": [{"window_id": 81}]}}},
    )
    assert isinstance(result, ToolResult)
    assert '"window_id": 81' in result.text


def test_malformed_structured_content_is_explicit_error():
    with pytest.raises(ValueError, match="structuredContent"):
        decode_tool_result("test", "read", {"result": {"structuredContent": []}})


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
