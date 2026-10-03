"""Summary inputs retain provenance and outcomes while excluding encoded images."""

from core.compaction_summary_sources import summary_source, shrink_summary_source


def test_source_projection_and_recursive_truncation_keep_tool_links():
    source = summary_source(
        {
            "id": "one",
            "role": "assistant",
            "content": "done",
            "media": ["image.png"],
            "llm_user_content": "private-base64",
            "tool_calls": [{"id": "call", "function": {"arguments": "x" * 1000}}],
            "tool_chain": [
                {"calls": [{"id": "call", "result": "head" + "z" * 12000 + "tail"}]}
            ],
        }
    )
    assert "llm_user_content" not in source
    assert source["media"] == ["image.png"]
    assert "chars truncated" in source["tool_chain"][0]["calls"][0]["result"]
    shrunk = shrink_summary_source(source, 200)
    assert shrunk["id"] == "one"
    assert shrunk["tool_calls"][0]["id"] == "call"
    assert len(shrunk["tool_calls"][0]["function"]["arguments"]) < 1000
    assert shrunk["tool_chain"][0]["calls"][0]["result"].endswith("tail")
