from memory2.query_builder import build_procedure_queries


def test_original_and_rewrite_are_normalized_in_order():
    assert build_procedure_queries("  下载\t视频 ", " 视频\n下载 SOP ") == [
        "下载 视频",
        "视频 下载 SOP",
    ]


def test_duplicates_after_whitespace_normalization_are_removed():
    assert build_procedure_queries(" hello\tworld ", "hello  world") == ["hello world"]


def test_empty_and_whitespace_queries_are_omitted():
    assert build_procedure_queries("", " \t\n") == []
    assert build_procedure_queries("  ", " 下载 ") == ["下载"]


def test_without_rewrite_returns_only_original():
    assert build_procedure_queries("帮我创建一个新技能") == ["帮我创建一个新技能"]
    assert build_procedure_queries("下载", "  ") == ["下载"]
