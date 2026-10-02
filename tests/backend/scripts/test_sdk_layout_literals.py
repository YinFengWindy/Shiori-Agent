"""Literals spelling repository directories are reported once, outside docs."""

import ast

from scripts.sdk_layout_literals import layout_literals


def _literals(source: str, judged: set[int] | None = None):
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    return layout_literals(nodes, parents, judged or set())


def test_repository_directories_in_literals_are_reported() -> None:
    assert _literals("asset = 'tests/backend/agent/fixtures.json'") == {
        "repository resource: tests/backend/agent/fixtures.json": 1
    }


def test_urls_prose_and_plugin_internal_paths_are_not_repository_paths() -> None:
    assert not _literals(
        "url = 'https://github.com/YinFengWindy/Shiori-Agent/tree/main/apps/backend/'\n"
        "note = 'Moved from apps/backend/ to the SDK.'\n"
        "data = 'plugins/x/tests/backend/data.json'\n"
    )


def test_docs_runtime_inputs_and_already_judged_literals_are_skipped() -> None:
    assert not _literals(
        "'apps/backend/ is the host'\nfile = tmp_path / 'apps/backend/x'"
    )
    tree = ast.parse("asset = 'apps/backend/x'")
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    assert not layout_literals(nodes, parents, {id(node) for node in nodes})
