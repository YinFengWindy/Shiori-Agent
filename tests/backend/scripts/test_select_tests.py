"""Path selection keeps the allowlist and widens on cross-module edits."""

from pathlib import Path
import subprocess
import sys

import pytest

from scripts.select_tests import (
    REPO_ROOT,
    changed_paths,
    discover_plugins,
    format_plan,
    materialize,
    plan,
    select,
)


def test_docs_and_desktop_stay_on_the_default_suite() -> None:
    selection = select(
        [
            "docs/knowledge/map.md",
            "AGENTS.md",
            "apps/site/src/pages/index.astro",
            "apps/desktop/renderer/src/app.tsx",
            "README.md",
            "plugins/tsconfig.json",
        ],
        plugins={},
    )
    assert selection.mode == "default"
    assert selection.host_paths == ()
    assert selection.external_paths == ()


def test_memory_change_pulls_agent() -> None:
    selection = select(["apps/backend/core/memory/runtime.py"], plugins={})
    assert selection.mode == "selected"
    assert "tests/backend/core/memory" in selection.host_paths
    assert "tests/backend/agent" in selection.host_paths
    assert "tests/backend/desktop_bridge" not in selection.host_paths


def test_agent_change_pulls_bridge_and_memory() -> None:
    selection = select(["apps/backend/agent/loop.py"], plugins={})
    assert selection.host_paths == (
        "tests/backend/agent",
        "tests/backend/core/memory",
        "tests/backend/desktop_bridge",
    )


def test_bridge_change_pulls_agent() -> None:
    selection = select(["apps/backend/desktop_bridge/dispatcher.py"], plugins={})
    assert "tests/backend/desktop_bridge" in selection.host_paths
    assert "tests/backend/agent" in selection.host_paths


def test_roles_change_pulls_agent_and_memory() -> None:
    selection = select(["apps/backend/core/roles/store.py"], plugins={})
    assert "tests/backend/core/roles" in selection.host_paths
    assert "tests/backend/agent" in selection.host_paths
    assert "tests/backend/core/memory" in selection.host_paths


def test_sdk_change_pulls_plugin_tests() -> None:
    selection = select(
        ["packages/sdk/python/shiori_sdk/memory/engine.py"],
        plugins={"qq": True, "story": True, "empty": False},
    )
    assert "packages/sdk/tests" in selection.external_paths
    assert "plugins/qq/tests" in selection.external_paths
    assert "plugins/story/tests" in selection.external_paths
    assert "plugins/empty/tests" not in selection.external_paths
    assert "tests/backend/agent/plugin_host" in selection.host_paths


def test_one_plugin_does_not_pull_every_plugin_or_the_sdk_suite() -> None:
    selection = select(
        ["plugins/qq/backend/channel.py"],
        plugins={"qq": True, "story": True},
    )
    assert selection.external_paths == ("plugins/qq/tests",)
    assert "tests/backend/agent/plugin_host" in selection.host_paths
    assert "packages/sdk/tests" not in selection.external_paths


def test_changed_extended_test_is_selected_without_widening_the_tree() -> None:
    path = "tests/backend/agent/core/passive_turn/test_reasoning_loop.py"
    selection = select([path], plugins={})
    assert selection.mode == "selected"
    assert selection.host_paths == (path,)


def test_docs_do_not_shrink_a_memory_change() -> None:
    selection = select(
        ["README.md", "apps/backend/core/memory/runtime.py"],
        plugins={},
    )
    assert "tests/backend/agent" in selection.host_paths


@pytest.mark.parametrize(
    "path",
    [
        "uv.lock",
        "pnpm-lock.yaml",
        ".github/workflows/ci.yml",
        "pytest.ini",
        "tests/support/default_suite.py",
        "scripts/select_tests.py",
        "apps/backend/requirements/development.txt",
        "apps/backend/utils/misc.py",
        "benchmarks/longmemeval/dataset.py",
        "tests/backend/memory_fakes.py",
        "tests/backend/agent/conftest.py",
    ],
)
def test_harness_and_unknown_sources_escalate(path: str) -> None:
    selection = select([path, "apps/backend/core/memory/runtime.py"], plugins={})
    assert selection.mode == "extended"
    assert selection.host_paths == ()


def test_format_plan_omits_paths_when_extended() -> None:
    selection = select(["uv.lock"], plugins={})
    assert format_plan(selection) == ("mode=extended",)


def test_format_plan_lists_neighbor_paths() -> None:
    selection = select(["apps/backend/desktop_bridge/router.py"], plugins={})
    text = "\n".join(format_plan(selection))
    assert text.startswith("mode=selected\n")
    assert "also=tests/backend/agent" in text
    assert "also=tests/backend/desktop_bridge" in text


def test_missing_neighbor_directory_escalates(tmp_path: Path) -> None:
    selection = select(["apps/backend/core/memory/store.py"], plugins={})
    assert materialize(selection, tmp_path).mode == "extended"


def test_materialize_keeps_existing_directories(tmp_path: Path) -> None:
    for relative in ("tests/backend/core/memory", "tests/backend/agent"):
        (tmp_path / relative).mkdir(parents=True)
    selection = select(["apps/backend/core/memory/store.py"], plugins={})
    resolved = materialize(selection, tmp_path)
    assert resolved.mode == "selected"
    assert resolved.host_paths == (
        "tests/backend/agent",
        "tests/backend/core/memory",
    )


def test_discover_plugins_sees_qq() -> None:
    found = discover_plugins(REPO_ROOT)
    assert found["qq"] is True


def test_changed_paths_follow_merge_base(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "checkout", "-b", "feature")
    memory = tmp_path / "apps" / "backend" / "core" / "memory"
    memory.mkdir(parents=True)
    (memory / "store.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "apps")
    _git(tmp_path, "commit", "-m", "memory")
    assert changed_paths(tmp_path) == ["apps/backend/core/memory/store.py"]


def test_plan_escalates_without_main(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "feature")
    assert plan(tmp_path).mode == "extended"


def test_also_collects_the_default_suite_and_the_named_file() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--also",
            "tests/backend/agent/core/passive_turn/test_reasoning_loop.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "test_reasoning_loop.py" in output
    assert "test_kernel.py" in output
    assert "test_agent_loop.py" not in output


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)
