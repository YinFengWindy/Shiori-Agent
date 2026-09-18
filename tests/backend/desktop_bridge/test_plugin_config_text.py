"""merge_plugin_table：定位-替换式合并 [plugins.<id>]，其余文本必须逐字节不变。"""

from __future__ import annotations

import tomllib

import pytest

from desktop_bridge.plugin_config_text import (
    PluginTableConflict,
    merge_plugin_table,
    remove_plugin_table,
)


def test_appends_a_new_table_when_missing():
    text = '[llm]\nmodel = "x"\n'

    result = merge_plugin_table(text, "demo", {"a": 1})

    assert result.startswith(text)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 1}
    assert parsed["llm"] == {"model": "x"}


@pytest.mark.parametrize(
    "text",
    [
        '[plugins.demo]\nnote = "delete"\n[plugins.other]\nkeep = true\n',
        '[plugins]\ndemo.note = "delete"\nother.keep = true\n',
        'plugins = { demo = { note = "delete" }, other = { keep = true } }\n',
    ],
)
def test_removes_plugin_settings_in_every_supported_toml_representation(text):
    config = text + '[llm]\nmodel = "retain"\n'
    result = remove_plugin_table(config, "demo")
    assert tomllib.loads(result) == {
        "plugins": {"other": {"keep": True}},
        "llm": {"model": "retain"},
    }


def test_removing_header_form_preserves_unrelated_text():
    config = '# comment\n[plugins.demo]\nnote = "delete"\n[plugins.other]\nkeep = true # keep comment\n'
    assert (
        remove_plugin_table(config, "demo")
        == "# comment\n[plugins.other]\nkeep = true # keep comment\n"
    )


def test_appends_to_an_empty_file():
    result = merge_plugin_table("", "demo", {"a": 1})

    assert tomllib.loads(result) == {"plugins": {"demo": {"a": 1}}}


def test_replaces_a_table_in_the_middle_of_the_file_and_preserves_the_rest():
    text = (
        "# top comment\n"
        "[llm]\n"
        'model = "x"\n'
        "\n"
        "[plugins.demo]\n"
        "a = 1\n"
        "old = true\n"
        "\n"
        "[plugins.other]\n"
        "z = 9\n"
        "\n"
        "[agent]\n"
        'foo = "bar"\n'
    )
    prefix = text[: text.index("[plugins.demo]")]
    suffix = text[text.index("[plugins.other]") :]

    result = merge_plugin_table(text, "demo", {"a": 2})

    # 目标表之前、之后的文本必须逐字节保留（含注释与不相关表）
    assert result.startswith(prefix)
    assert result.endswith(suffix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert "old" not in parsed["plugins"]["demo"]
    assert parsed["plugins"]["other"] == {"z": 9}
    assert parsed["agent"] == {"foo": "bar"}


def test_replaces_a_table_at_the_end_of_the_file():
    text = '[llm]\nmodel = "x"\n\n[plugins.demo]\na = 1\n'
    prefix = text[: text.index("[plugins.demo]")]

    result = merge_plugin_table(text, "demo", {"a": 2, "b": "hi"})

    assert result.startswith(prefix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2, "b": "hi"}


def test_replaces_a_table_without_a_trailing_newline_in_the_source():
    text = '[llm]\nmodel = "x"\n\n[plugins.demo]\na = 1'

    result = merge_plugin_table(text, "demo", {"a": 3})

    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 3}


def test_replaces_own_subtables_but_leaves_siblings_untouched():
    text = (
        "[plugins.demo]\n"
        "a = 1\n"
        "\n"
        "[plugins.demo.sub]\n"
        "old = true\n"
        "\n"
        "[plugins.other]\n"
        "z = 9\n"
    )
    suffix = text[text.index("[plugins.other]") :]

    result = merge_plugin_table(text, "demo", {"a": 2, "sub": {"new": True}})

    assert result.endswith(suffix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2, "sub": {"new": True}}
    assert parsed["plugins"]["other"] == {"z": 9}


def test_rendered_values_round_trip_through_toml_parsing():
    values = {
        "text": "hello",
        "flag": False,
        "count": 7,
        "items": ["a", "b"],
        "nested": {"inner": 1.5},
    }

    result = merge_plugin_table("", "demo", values)

    assert tomllib.loads(result)["plugins"]["demo"] == values


def test_a_plugin_id_that_is_a_prefix_of_another_does_not_collide():
    text = "[plugins.foo]\n" "value = 1\n" "\n" "[plugins.foobar]\n" "value = 2\n"

    result = merge_plugin_table(text, "foo", {"value": 3})

    parsed = tomllib.loads(result)
    assert parsed["plugins"]["foo"] == {"value": 3}
    assert parsed["plugins"]["foobar"] == {"value": 2}


def test_a_multi_line_arrays_lone_last_element_is_not_mistaken_for_a_header():
    """回归：``[3]`` 独占一行时，旧的逐行正则会把它误判成表头。

    这会让 ``end`` 提前锁定在这一行，导致目标表之后、真正下一个表之前的
    全部内容（这里是 ``[other]``）被当作"已替换区间"的一部分丢弃。
    """
    text = (
        "[plugins.demo]\n"
        "a = 1\n"
        "matrix = [\n"
        "  [1, 2],\n"
        "  [3]\n"
        "]\n"
        "\n"
        "[other]\n"
        "z = 9\n"
    )
    suffix = text[text.index("[other]") :]

    result = merge_plugin_table(text, "demo", {"a": 2})

    assert result.endswith(suffix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert parsed["other"] == {"z": 9}


def test_a_header_shaped_line_inside_a_multiline_basic_string_is_not_a_header():
    """回归：三引号字符串内部的 ``[a.b]`` 不能被当成表头解析。"""
    text = (
        "[plugins.demo]\n"
        "a = 1\n"
        'note = """\n'
        "[a.b]\n"
        "more text\n"
        '"""\n'
        "\n"
        "[other]\n"
        "z = 9\n"
    )
    suffix = text[text.index("[other]") :]

    result = merge_plugin_table(text, "demo", {"a": 2})

    assert result.endswith(suffix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert parsed["other"] == {"z": 9}


def test_a_header_shaped_line_inside_a_multiline_literal_string_is_not_a_header():
    """三引号字面量字符串（无转义）同样不能被误判成表头。"""
    text = (
        "[plugins.demo]\n"
        "a = 1\n"
        "note = '''\n"
        "[a.b]\n"
        "'''\n"
        "\n"
        "[other]\n"
        "z = 9\n"
    )
    suffix = text[text.index("[other]") :]

    result = merge_plugin_table(text, "demo", {"a": 2})

    assert result.endswith(suffix)
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert parsed["other"] == {"z": 9}


def test_a_header_line_with_a_trailing_comment_is_located_and_replaced():
    """回归：行尾注释曾让表头正则的末尾锚点失配，导致误判为"不存在"，

    从而走 append 分支，在文件末尾追加出一张重复的 ``[plugins.demo]``。
    """
    text = "[plugins.demo]  # 说明文字\na = 1\n\n[other]\nz = 9\n"

    result = merge_plugin_table(text, "demo", {"a": 2})

    # 只应该有一张 [plugins.demo]，而不是替换失败后又追加了一张
    assert result.count("[plugins.demo]") == 1
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert parsed["other"] == {"z": 9}


def test_a_quoted_key_header_is_located_by_its_unquoted_value():
    """带引号的键（``plugin_id`` 本身含点）不能靠原始文本前缀匹配。"""
    text = '[plugins."my.plugin"]\na = 1\n\n[other]\nz = 9\n'

    result = merge_plugin_table(text, "my.plugin", {"a": 2})

    assert result.count('"my.plugin"') == 1
    parsed = tomllib.loads(result)
    assert parsed["plugins"]["my.plugin"] == {"a": 2}
    assert parsed["other"] == {"z": 9}


def test_replaces_owned_subtables_separated_by_an_unrelated_table():
    """目标插件的主表与子表之间夹着无关表时，后面的旧子表也必须被替换掉。

    TOML 不要求同一张表的子表紧跟主表，两种顺序解析结果完全一样。只处理第一段
    连续区间会把后面的旧子表留在原地，与新写入的子表构成重复表声明，整份文档
    随即无法解析——写入被拒，用户的插件配置永远存不上。
    """
    original = (
        "[plugins.demo]\n"
        "a = 1\n"
        "\n"
        "[plugins.other]\n"
        "keep = true\n"
        "\n"
        "[plugins.demo.nested]\n"
        "b = 2\n"
    )

    merged = merge_plugin_table(original, "demo", {"a": 9, "nested": {"b": 8}})

    parsed = tomllib.loads(merged)
    assert parsed["plugins"]["demo"] == {"a": 9, "nested": {"b": 8}}
    assert parsed["plugins"]["other"] == {"keep": True}
    # 旧子表不得残留（残留会造成重复表声明）
    assert merged.count("[plugins.demo.nested]") == 1


def test_a_dotted_key_form_under_plugins_is_rejected_not_duplicated():
    """``[plugins]`` 表下用点分键写目标插件（合法 TOML）时，定位器找不到独立
    表头，必须拒绝而不是追加出一份重复的 ``[plugins.demo]`` 声明。

    追加会让文档同时持有 ``plugins.demo`` 的两份声明（点分键赋的一份、新追加
    表头的一份），随即无法被 ``tomllib`` 解析——用户的写入被一个看不懂的解析
    错误挡住，而不是一个指向真实原因（点分键）的错误。
    """
    text = "[plugins]\ndemo.a = 1\n"

    with pytest.raises(PluginTableConflict):
        merge_plugin_table(text, "demo", {"a": 2})


def test_an_inline_table_form_under_plugins_is_rejected_not_duplicated():
    text = "plugins = { demo = { a = 1 } }\n"

    with pytest.raises(PluginTableConflict):
        merge_plugin_table(text, "demo", {"a": 2})


def test_a_genuinely_new_plugin_id_still_appends_normally_despite_the_new_guard():
    """点分键守卫只应拦截"目标插件已经以定位不到的形式存在"的情况；一个从未
    出现过的 plugin_id 必须继续正常走追加路径。
    """
    text = "[plugins]\nother.a = 1\n"

    result = merge_plugin_table(text, "demo", {"a": 2})

    parsed = tomllib.loads(result)
    assert parsed["plugins"]["demo"] == {"a": 2}
    assert parsed["plugins"]["other"] == {"a": 1}


def test_a_malformed_original_document_does_not_crash_the_new_guard():
    """新守卫在检测点分键冲突前会尝试解析整份原文；原文若本就无法解析，必须
    安静地放弃检测（把报错留给下游更清楚的回读守卫），而不是让 ``tomllib``
    的解析异常从这里逃出去。
    """
    text = "[plugins\ndemo = 1\n"

    result = merge_plugin_table(text, "demo", {"a": 2})

    assert "[plugins.demo]" in result
