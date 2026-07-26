from desktop_bridge.tts_text import TtsSentenceBuffer, split_tts_sentences


def test_split_tts_sentences_removes_markdown_and_limits_chunks() -> None:
    sentences = split_tts_sentences("# 标题\n你好。`代码`，" + "很长" * 50 + "！")

    assert sentences[0] == "标题 你好。"
    assert sentences[1].startswith("代码，")
    assert all(len(sentence) <= 80 for sentence in sentences)


def test_tts_sentence_buffer_flushes_only_complete_sentences() -> None:
    buffer = TtsSentenceBuffer()

    assert buffer.push("你好") == []
    assert buffer.push("，今天怎么样？下一句") == ["你好，今天怎么样？"]
    assert buffer.finish() == ["下一句"]


def test_tts_sentence_buffer_drops_fenced_code_before_speaking() -> None:
    buffer = TtsSentenceBuffer()

    assert buffer.push("先说。```python\nprint('x')。\n```") == ["先说。"]
    assert buffer.push("然后说！") == ["然后说！"]
    assert buffer.finish() == []


def test_split_tts_sentences_filters_parenthetical_details_and_emoji() -> None:
    assert split_tts_sentences("（轻轻笑了笑）你好😊。😏") == ["你好。"]


def test_split_tts_sentences_filters_ascii_parenthetical_details() -> None:
    assert split_tts_sentences("Hello (thinking: wait. really?) world!") == [
        "Hello world!"
    ]


def test_split_tts_sentences_drops_non_spoken_symbols() -> None:
    assert split_tts_sentences("😏……！！！") == []


def test_tts_sentence_buffer_ignores_boundaries_inside_parentheses() -> None:
    buffer = TtsSentenceBuffer()

    assert buffer.push("（轻声。") == []
    assert buffer.push("）你好。") == ["你好。"]
    assert buffer.finish() == []
