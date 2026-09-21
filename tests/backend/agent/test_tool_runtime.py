from __future__ import annotations

from agent.tool_runtime import append_tool_result
from agent.tools.base import ToolResult


def test_append_tool_result_supports_multimodal_blocks() -> None:
    messages: list[dict] = []
    append_tool_result(
        messages,
        tool_call_id="call_1",
        tool_name="read_file",
        content=ToolResult(
            text="[已读取图片文件 a.png，图片内容已提供给多模态模型]",
            content_blocks=[
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                }
            ],
        ),
    )
    assert messages[0]["role"] == "tool"
    assert messages[0]["content"].startswith("[已读取图片文件")
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0]["type"] == "text"
    assert messages[1]["content"][1]["type"] == "image_url"


def test_append_batch_tool_results_precedes_all_images():
    messages = [{"role": "assistant", "tool_calls": [{"id": "one"}, {"id": "two"}]}]
    append_tool_result(
        messages,
        tool_call_id="one",
        content=ToolResult(
            content_blocks=[
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                }
            ]
        ),
    )
    append_tool_result(messages, tool_call_id="two", content="second result")
    assert [message["role"] for message in messages] == [
        "assistant",
        "tool",
        "tool",
        "user",
    ]
    assert messages[1]["tool_call_id"] == "one"
    assert messages[2]["tool_call_id"] == "two"
