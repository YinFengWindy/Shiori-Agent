from agent.prompting.token_estimate import estimate_input, estimate_tokens


def test_chinese_and_images_are_not_counted_as_json_or_base64_text():
    assert estimate_tokens("你好" * 100) >= 200

    def image(url):
        return {"type": "image_url", "image_url": {"url": url}}

    assert (
        estimate_tokens(image("data:image/png;base64," + "a" * 100000))
        == estimate_tokens(image("https://example.test/a.png"))
        > 0
    )
    assert (
        estimate_tokens(
            {"type": "image_url", "image_url": {"url": "x", "detail": "low"}}
        )
        == 85
    )


def test_complete_input_contains_schema_retrieval_current_text_and_image_once():
    messages = [
        {"role": "system", "content": "固定约束"},
        {"role": "user", "content": "检索记忆"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "当前输入"},
                {"type": "image_url", "image_url": {"url": "x"}},
            ],
        },
    ]
    tools = [
        {"type": "function", "function": {"name": "read", "description": "读取资料"}}
    ]
    assert estimate_input(messages, tools) == estimate_tokens(
        {"messages": messages, "tools": tools}
    )
    assert estimate_input(messages, tools) > estimate_input(messages)
