"""Dependency selection and parallel scheduling for the external plugin test runner."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pytest

from scripts import verify_plugin_tests as runner


def _plugin(
    repository: Path,
    plugin_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    optional: dict[str, tuple[str, ...]] | None = None,
) -> None:
    path = repository / "plugins" / plugin_id / "pyproject.toml"
    path.parent.mkdir(parents=True)
    text = (
        f'[project]\nname = "shiori-plugin-{plugin_id.replace("_", "-")}"\n'
        f"dependencies = {json.dumps(dependencies)}\n"
    )
    if optional:
        text += "[project.optional-dependencies]\n"
        text += "".join(
            f"{json.dumps(extra)} = {json.dumps(requirements)}\n"
            for extra, requirements in optional.items()
        )
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runner, "REPOSITORY", tmp_path)
    _plugin(tmp_path, "default_memory")
    return tmp_path


def test_target_test_only_dependency_is_added_without_changing_runtime(
    repository: Path,
) -> None:
    _plugin(
        repository,
        "status_commands",
        dependencies=("shiori-agent==0.1.0",),
        optional={
            "test": ("shiori-plugin-testkit==0.1.0", "shiori-plugin-observe==0.1.0")
        },
    )
    _plugin(repository, "observe")

    assert runner.plugin_dependencies({"status_commands"}) == {
        "status_commands",
        "default_memory",
    }
    assert runner.plugin_dependencies(
        {"status_commands"}, extras=frozenset({"test"})
    ) == {"status_commands", "default_memory", "observe"}
    # There is deliberately no plugins/testkit directory in this repository.
    assert not (repository / "plugins/testkit").exists()


def test_sibling_runtime_chain_does_not_inherit_target_test_extra(
    repository: Path,
) -> None:
    _plugin(repository, "target", optional={"test": ("shiori-plugin-observe",)})
    _plugin(
        repository,
        "observe",
        dependencies=("shiori-plugin-citation",),
        optional={"test": ("shiori-plugin-unrequested",)},
    )
    _plugin(repository, "citation", dependencies=("shiori-plugin-target",))

    assert runner.plugin_dependencies({"target"}, extras=frozenset({"test"})) == {
        "target",
        "default_memory",
        "observe",
        "citation",
    }


def test_explicit_sibling_extra_is_processed_after_its_runtime_context(
    repository: Path,
) -> None:
    _plugin(
        repository,
        "target",
        dependencies=("shiori-plugin-observe[test]", "shiori-plugin-observe"),
    )
    _plugin(repository, "observe", optional={"test": ("shiori-plugin-audit",)})
    _plugin(repository, "audit")

    assert runner.plugin_dependencies({"target"}) == {
        "target",
        "default_memory",
        "observe",
        "audit",
    }


@pytest.mark.parametrize(
    "marker",
    ['python_version < "3"', 'sys_platform == "unavailable"', 'extra == "other"'],
)
def test_inactive_markers_do_not_require_missing_plugin_directories(
    repository: Path, marker: str
) -> None:
    _plugin(
        repository,
        "target",
        optional={"test": (f"shiori-plugin-unavailable; {marker}",)},
    )

    assert runner.plugin_dependencies({"target"}, extras=frozenset({"test"})) == {
        "target",
        "default_memory",
    }


def test_markers_use_the_active_extra_and_preserve_base_runtime_dependencies(
    repository: Path,
) -> None:
    _plugin(
        repository,
        "target",
        dependencies=(
            'shiori-plugin-runtime; extra != "test"',
            'shiori-plugin-observe; extra == "test" and python_version >= "3"',
        ),
        optional={
            "test": ("Shiori_Plugin_Testkit", "shiori-plugin-citation[render_tools]")
        },
    )
    _plugin(repository, "runtime")
    _plugin(repository, "observe")
    _plugin(
        repository,
        "citation",
        optional={"render-tools": ('shiori-plugin-audit; extra == "render_tools"',)},
    )
    _plugin(repository, "audit")

    assert runner.plugin_dependencies({"target"}, extras=frozenset({"test"})) == {
        "target",
        "default_memory",
        "runtime",
        "observe",
        "citation",
        "audit",
    }


def _fake_verify(
    calls: list[str], *, command_failure: str = "", assertion_failure: str = ""
) -> Callable[[str], dict[str, object]]:
    """Stands in for verify_plugin, failing the chosen plugins the two real ways."""

    def verify(plugin_id: str) -> dict[str, object]:
        calls.append(plugin_id)
        if plugin_id == command_failure:
            raise runner.CommandFailed(
                "Expected exit 0, got 1; see pytest.log\nlog tail",
                log=Path("cases", plugin_id, "pytest.log"),
            )
        if plugin_id == assertion_failure:
            # Like the bare asserts in verify_plugin: no message at all.
            raise AssertionError()
        return {"plugin": plugin_id, "result": "3 passed"}

    return verify


def test_slow_plugins_are_scheduled_first_and_the_rest_keep_order() -> None:
    assert runner.schedule(["alpha", "qqbot", "beta", "telegram", "feishu"]) == [
        "qqbot",
        "telegram",
        "feishu",
        "alpha",
        "beta",
    ]


def test_failures_do_not_stop_other_plugins_and_results_are_sorted() -> None:
    calls: list[str] = []

    results = runner.verify_all(
        ["zeta", "broken", "alpha", "crash"],
        _fake_verify(calls, command_failure="broken", assertion_failure="crash"),
        jobs=2,
    )

    assert sorted(calls) == ["alpha", "broken", "crash", "zeta"]
    assert [entry["plugin"] for entry in results] == [
        "alpha",
        "broken",
        "crash",
        "zeta",
    ]
    by_id = {entry["plugin"]: entry for entry in results}
    assert by_id["alpha"]["status"] == "passed"
    assert by_id["alpha"]["result"] == "3 passed"
    assert by_id["broken"] == {
        "plugin": "broken",
        "status": "failed",
        "error": "Expected exit 0, got 1; see pytest.log",
        "log": str(Path("cases", "broken", "pytest.log")),
        "seconds": by_id["broken"]["seconds"],
    }
    # Assertion failures inside verify_plugin carry no command log.
    assert by_id["crash"]["status"] == "failed"
    assert by_id["crash"]["error"] == "AssertionError"
    assert by_id["crash"]["log"] is None
    assert all(isinstance(entry["seconds"], float) for entry in results)


def test_main_summarizes_all_failures_writes_results_and_exits_non_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    for plugin_id in ("alpha", "broken", "crash", "telegram"):
        _plugin(repository, plugin_id)
    _plugin(repository, "default_memory")
    monkeypatch.setattr(runner, "REPOSITORY", repository)
    monkeypatch.setattr(runner, "stage_plugin_package", lambda source, target: target)
    built: list[str] = []

    def build_wheel(source: Path, destination: Path, log: Path) -> Path:
        built.append(log.name)
        return destination / f"{source.name}.whl"

    monkeypatch.setattr(runner, "build_wheel", build_wheel)
    monkeypatch.setattr(runner, "check_host_wheel", lambda wheel, log: None)
    calls: list[str] = []
    fake = _fake_verify(calls, command_failure="broken", assertion_failure="crash")
    monkeypatch.setattr(runner, "verify_plugin", lambda plugin_id, **_: fake(plugin_id))
    output = tmp_path / "evidence"

    with pytest.raises(SystemExit) as exited:
        runner.main(
            [
                "--output",
                str(output),
                "--plugins",
                "telegram",
                "crash",
                "broken",
                "alpha",
                "--jobs",
                "3",
            ]
        )

    assert exited.value.code == 1
    assert sorted(calls) == ["alpha", "broken", "crash", "telegram"]
    assert sorted(built) == [
        "build-alpha.log",
        "build-broken.log",
        "build-crash.log",
        "build-default_memory.log",
        "build-host.log",
        "build-telegram.log",
        "build-testkit.log",
    ]
    results = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert [(entry["plugin"], entry["status"]) for entry in results] == [
        ("alpha", "passed"),
        ("broken", "failed"),
        ("crash", "failed"),
        ("telegram", "passed"),
    ]
    summary = capsys.readouterr().out.split("2 of 4 plugin suites failed:\n")[1]
    assert summary.splitlines() == [
        f"  broken: {Path('cases', 'broken', 'pytest.log')}",
        "  crash: AssertionError",
    ]


def test_jobs_defaults_to_cpu_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pool size reaches both the wheel builds and the verification pool."""
    received: list[int] = []

    def build_wheels(sources, wheelhouse, logs, *, jobs: int):
        received.append(jobs)
        raise SystemExit(0)

    monkeypatch.setattr(runner, "REPOSITORY", tmp_path / "repository")
    _plugin(tmp_path / "repository", "alpha")
    _plugin(tmp_path / "repository", "default_memory")
    monkeypatch.setattr(runner, "stage_plugin_package", lambda source, target: target)
    monkeypatch.setattr(runner, "build_wheels", build_wheels)
    monkeypatch.setattr(runner.os, "cpu_count", lambda: 7)

    with pytest.raises(SystemExit):
        runner.main(["--output", str(tmp_path / "out"), "--plugins", "alpha"])

    assert received == [7]
