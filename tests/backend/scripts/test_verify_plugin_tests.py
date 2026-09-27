"""Dependency selection and parallel scheduling for the external plugin test runner."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import time

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


def test_failures_do_not_stop_other_plugins_and_results_are_sorted(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    results = runner.verify_all(
        ["zeta", "broken", "alpha", "crash"],
        _fake_verify(calls, command_failure="broken", assertion_failure="crash"),
        artifact_root=tmp_path,
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
    # A failed command is reported with its own output log.
    assert by_id["broken"] == {
        "plugin": "broken",
        "status": "failed",
        "error": "Expected exit 0, got 1; see pytest.log",
        "log": str(Path("cases", "broken", "pytest.log")),
        "seconds": by_id["broken"]["seconds"],
    }
    assert not (tmp_path / "cases" / "broken" / "failure.log").exists()
    assert all(isinstance(entry["seconds"], float) for entry in results)
    written = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert written == results


def test_non_command_failure_keeps_its_full_traceback_as_the_log(
    tmp_path: Path,
) -> None:
    results = runner.verify_all(
        ["crash"],
        _fake_verify([], assertion_failure="crash"),
        artifact_root=tmp_path,
        jobs=1,
    )

    log = tmp_path / "cases" / "crash" / "failure.log"
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "AssertionError"
    assert results[0]["log"] == str(log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("Traceback (most recent call last):")
    # The traceback points at the raising line, which the one-line error cannot.
    assert "raise AssertionError()" in text


def test_verify_fields_cannot_override_the_runner_owned_status(
    tmp_path: Path,
) -> None:
    results = runner.verify_all(
        ["alpha"],
        lambda plugin_id: {"plugin": "other", "status": "failed", "result": "ok"},
        artifact_root=tmp_path,
        jobs=1,
    )

    assert results[0]["plugin"] == "alpha"
    assert results[0]["status"] == "passed"
    assert results[0]["result"] == "ok"


def test_results_are_written_as_each_plugin_completes(tmp_path: Path) -> None:
    """A run killed mid-way (e.g. by the CI timeout) still leaves partial evidence."""
    results_file = tmp_path / "results.json"
    seen_while_running: list[object] = []

    def verify(plugin_id: str) -> dict[str, object]:
        if plugin_id == "slow":
            # Wait until the main thread has recorded the fast plugin. The file is
            # replaced atomically, so every read here sees complete JSON.
            deadline = time.monotonic() + 5
            recorded = json.loads(results_file.read_text(encoding="utf-8"))
            while not recorded and time.monotonic() < deadline:
                time.sleep(0.01)
                recorded = json.loads(results_file.read_text(encoding="utf-8"))
            seen_while_running.append(recorded)
        return {"result": "1 passed"}

    runner.verify_all(["fast", "slow"], verify, artifact_root=tmp_path, jobs=2)

    assert len(seen_while_running) == 1
    partial = seen_while_running[0]
    assert isinstance(partial, list)
    assert [entry["plugin"] for entry in partial] == ["fast"]
    final = json.loads(results_file.read_text(encoding="utf-8"))
    assert [entry["plugin"] for entry in final] == ["fast", "slow"]


def test_empty_plugin_selection_still_writes_results(tmp_path: Path) -> None:
    assert (
        runner.verify_all([], lambda plugin_id: {}, artifact_root=tmp_path, jobs=1)
        == []
    )

    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8")) == []


def test_interrupted_results_write_keeps_the_previous_complete_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A kill mid-write must not leave truncated JSON behind."""
    runner.write_results(tmp_path, [{"plugin": "alpha", "status": "passed"}])
    original = Path.write_text

    def killed_mid_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        original(self, data[: len(data) // 2], encoding="utf-8")
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", killed_mid_write)
    with pytest.raises(KeyboardInterrupt):
        runner.write_results(tmp_path, [{"plugin": "beta", "status": "passed"}])
    monkeypatch.undo()

    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8")) == [
        {"plugin": "alpha", "status": "passed"}
    ]


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
    # Every failed plugin is listed with a log path.
    summary = capsys.readouterr().out.split("2 of 4 plugin suites failed:\n")[1]
    assert summary.splitlines() == [
        f"  broken: {Path('cases', 'broken', 'pytest.log')}",
        f"  crash: {output / 'cases' / 'crash' / 'failure.log'}",
    ]


def test_jobs_defaults_to_cpu_count_for_builds_and_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default pool size reaches both the wheel builds and the verification pool."""
    received: dict[str, int] = {}

    def build_wheels(
        sources: dict[str, Path], wheelhouse: Path, logs: Path, *, jobs: int
    ) -> dict[str, Path]:
        received["build"] = jobs
        return {name: wheelhouse / f"{name}.whl" for name in sources}

    def verify_all(
        plugin_ids: list[str],
        verify: Callable[[str], dict[str, object]],
        *,
        artifact_root: Path,
        jobs: int,
    ) -> list[dict[str, object]]:
        received["verify"] = jobs
        return []

    monkeypatch.setattr(runner, "REPOSITORY", tmp_path / "repository")
    _plugin(tmp_path / "repository", "alpha")
    _plugin(tmp_path / "repository", "default_memory")
    monkeypatch.setattr(runner, "stage_plugin_package", lambda source, target: target)
    monkeypatch.setattr(runner, "build_wheels", build_wheels)
    monkeypatch.setattr(runner, "check_host_wheel", lambda wheel, log: None)
    monkeypatch.setattr(runner, "verify_all", verify_all)
    monkeypatch.setattr(runner.os, "cpu_count", lambda: 7)

    runner.main(["--output", str(tmp_path / "out"), "--plugins", "alpha"])

    assert received == {"build": 7, "verify": 7}
