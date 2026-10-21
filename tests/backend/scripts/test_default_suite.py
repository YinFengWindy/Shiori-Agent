"""The default host selection stays inside its case budget and on real files."""

from tests.support.default_suite import (
    DEFAULT_CASE_MAX,
    DEFAULT_CASE_MIN,
    DEFAULT_DIRECTORIES,
    DEFAULT_FILES,
    REPO_ROOT,
    count_default_cases,
    is_default_test,
    selection_is_default_root,
    should_ignore_collect,
)


def test_allowlist_paths_exist() -> None:
    for directory in DEFAULT_DIRECTORIES:
        assert (REPO_ROOT / directory).is_dir(), directory
    for relative in DEFAULT_FILES:
        assert (REPO_ROOT / relative).is_file(), relative


def test_default_case_count_stays_near_one_thousand() -> None:
    count = count_default_cases()
    assert DEFAULT_CASE_MIN <= count <= DEFAULT_CASE_MAX, count


def test_extended_host_file_is_ignored_on_the_default_root() -> None:
    assert should_ignore_collect(
        "tests/backend/agent/core/passive_turn/test_reasoning_loop.py", is_dir=False
    )
    assert not should_ignore_collect(
        "tests/backend/agent/plugin_host/test_kernel.py", is_dir=False
    )
    assert not should_ignore_collect("tests/backend/conftest.py", is_dir=False)
    assert should_ignore_collect("tests/backend/benchmarks", is_dir=True)
    assert not should_ignore_collect("tests/backend/agent/lifecycle", is_dir=True)


def test_explicit_path_is_not_the_default_root() -> None:
    root = REPO_ROOT
    assert selection_is_default_root([], cwd=root, root=root)
    assert selection_is_default_root(["tests/backend"], cwd=root, root=root)
    assert not selection_is_default_root(
        ["tests/backend/agent/core/passive_turn/test_reasoning_loop.py"],
        cwd=root,
        root=root,
    )
    assert not selection_is_default_root(["plugins/qq/tests"], cwd=root, root=root)


def test_kernel_contract_stays_on_the_default_path() -> None:
    assert is_default_test("tests/backend/agent/plugin_host/test_kernel.py")
    assert not is_default_test(
        "tests/backend/agent/core/passive_turn/test_reasoning_loop.py"
    )


def test_pytest_ini_declares_extended_and_drops_unused_markers() -> None:
    text = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "extended:" in text
    assert "testpaths = tests/backend" in text
    for retired in (
        "scenario_mvp",
        "scenario_live",
        "proactive_scenario",
        "scenario_routing",
        "live_replay",
    ):
        assert retired not in text
