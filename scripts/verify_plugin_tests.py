"""Build private wheels and run every plugin in a separate repository-external venv."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import tomllib
import traceback
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from packaging.utils import canonicalize_name, parse_wheel_filename
from shiori_sdk.testing.packages import stage_plugin_package

from scripts.commands import UV, CommandFailed, run
from scripts.sdk_boundaries import (
    HOST_DISTRIBUTIONS,
    LOCAL_DISTRIBUTION_PREFIX,
    PLUGIN_DISTRIBUTION_PREFIX,
    host_roots,
    plugin_distribution,
    plugin_id_of,
)
from scripts.wheelhouse import install_from_wheelhouse, requirement_closure

REPOSITORY = Path(__file__).resolve().parents[1]
SLOW_PLUGINS = ("telegram", "feishu", "qqbot")


def build_wheel(source: Path, destination: Path, log: Path) -> Path:
    """Builds a non-editable wheel from the specified package source."""
    run(
        [UV, "build", "--wheel", "--out-dir", str(destination), str(source)],
        cwd=source,
        log=log,
    )
    metadata = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    prefix = metadata["project"]["name"].replace("-", "_") + "-"
    return next(
        path for path in destination.glob("*.whl") if path.name.startswith(prefix)
    )


def build_wheels(
    sources: Mapping[str, Path], wheelhouse: Path, logs: Path, *, jobs: int
) -> dict[str, Path]:
    """Builds every package concurrently into the shared wheelhouse.

    Each source writes build state only in its own directory, and wheel lookup keys
    on the distinct ``<name>-`` prefix, so concurrent builds cannot collide.
    """
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            name: pool.submit(
                build_wheel, source, wheelhouse, logs / f"build-{name}.log"
            )
            for name, source in sources.items()
        }
        return {name: future.result() for name, future in futures.items()}


def write_provenance_probe(
    case: Path,
    modules: dict[str, str],
    allowed: list[str],
    *,
    source_packages: Iterable[Path],
    wheelhouse: Path,
) -> None:
    """Copy a standalone probe; the child never imports runner code from the checkout."""
    shutil.copyfile(
        REPOSITORY / "scripts/isolation_probe.py", case / "verify_provenance.py"
    )
    config = {
        "repository": str(REPOSITORY),
        # pytest owns an external tests namespace; static plugin imports of host
        # tests remain forbidden, and loaded module paths are audited separately.
        "host_roots": sorted(host_roots(REPOSITORY) - {"tests"}),
        "allowed_plugins": allowed,
        "modules": modules,
        "source_packages": sorted(str(source.resolve()) for source in source_packages),
        # Every installed shiori-* distribution must come from these wheel files.
        "wheelhouse": str(wheelhouse.resolve()),
        # The probe is copied stdlib-only, so naming rules arrive as data.
        "local_prefix": LOCAL_DISTRIBUTION_PREFIX,
        "plugin_prefix": PLUGIN_DISTRIBUTION_PREFIX,
        "host_distributions": sorted(HOST_DISTRIBUTIONS),
        "sdk_version": json.loads(
            (REPOSITORY / "packages/sdk/package.json").read_text(encoding="utf-8")
        )["version"],
    }
    (case / "isolation.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def case_directory(artifact_root: Path, plugin_id: str) -> Path:
    """Holds every piece of per-plugin evidence (venv, logs, provenance)."""
    return artifact_root / "cases" / plugin_id


def verify_plugin(
    plugin_id: str,
    *,
    artifact_root: Path,
    wheelhouse: Path,
    sources: Mapping[str, Path],
    wheel: Path,
) -> dict[str, object]:
    """Runs all target tests with only the target and its declared sibling dependencies installed."""
    case = case_directory(artifact_root, plugin_id)
    case.mkdir(parents=True)
    source = sources[plugin_id]
    venv = case / "venv"
    run(
        [UV, "venv", "--python", sys.executable, str(venv)],
        cwd=case,
        log=case / "venv.log",
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install_from_wheelhouse(
        python,
        wheelhouse,
        [f"{parse_wheel_filename(wheel.name)[0]}[test]"],
        cwd=case,
        log=case / "install.log",
    )
    ids = plugin_dependencies({plugin_id}, extras=frozenset({"test"}))
    allowed = [plugin_distribution(name) for name in sorted(ids)]
    write_provenance_probe(
        case,
        {
            f"plugins.{name}.backend.plugin": str(sources[name] / "backend/plugin.py")
            for name in sorted(ids)
        },
        allowed,
        # Other targets also coexist in the artifact's staging directory. No
        # test may execute their uninstalled implementations through an alias.
        source_packages=sources.values(),
        wheelhouse=wheelhouse,
    )
    output = run(
        [
            str(python),
            "-m",
            "pytest",
            # Concurrent case processes must not clean pytest's shared temp root.
            "--basetemp",
            str(case / "pytest-tmp"),
            "-p",
            "verify_provenance",
            "-c",
            str(source / "pyproject.toml"),
            str(source / "tests"),
            "-q",
            "-W",
            "error",
        ],
        cwd=case,
        log=case / "pytest.log",
    )
    # A separate fresh interpreter must await an intentionally failing coroutine.
    probe = case / "test_async_failure.py"
    probe.write_text(
        "import asyncio\nfrom pathlib import Path\nimport pytest\n\n@pytest.mark.asyncio\nasync def test_failure_after_await():\n    await asyncio.sleep(0)\n    Path('awaited.txt').write_text('awaited', encoding='utf-8')\n    assert False, 'expected async failure probe'\n",
        encoding="utf-8",
    )
    failure = run(
        [
            str(python),
            "-m",
            "pytest",
            # Keep probe cleanup separate from this case's suite evidence too.
            "--basetemp",
            str(case / "async-failure-tmp"),
            "-c",
            str(source / "pyproject.toml"),
            str(probe),
            "-q",
            "-W",
            "error",
        ],
        cwd=case,
        log=case / "async-failure.log",
        expected=1,
    )
    assert (case / "awaited.txt").read_text(encoding="utf-8") == "awaited"
    assert "1 failed" in failure and "expected async failure probe" in failure
    return {
        "plugin": plugin_id,
        "result": output.splitlines()[-1],
        "venv": str(venv),
        "async_failure_proved": True,
    }


def plugin_dependencies(
    plugin_ids: set[str],
    *,
    extras: frozenset[str] = frozenset(),
) -> set[str]:
    """Resolves selected extras and declared sibling dependencies for this interpreter.

    Runtime requirements always apply. Each requested extra adds its own optional
    requirements; siblings receive only extras explicitly requested on their edge.
    Host/testkit requirements are rejected, including requirements on selected extras.
    """

    def declared(name: str, extra: str) -> list[str] | None:
        directory = plugin_id_of(name)
        if directory is None:
            return None
        project = tomllib.loads(
            (REPOSITORY / "plugins" / directory / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )["project"]
        requirements = list(project.get("dependencies", []))
        # Optional groups are evaluated in their own active extra context. Runtime
        # requirements also get the base context, matching normal package installs.
        for group, optional in project.get("optional-dependencies", {}).items():
            if extra and canonicalize_name(group) == extra:
                requirements.extend(optional)
        return requirements

    selected = ",".join(sorted(extras))
    roots = [
        plugin_distribution(plugin) + (f"[{selected}]" if selected else "")
        for plugin in plugin_ids
    ]
    local, external = requirement_closure(roots, declared)
    for declarer, requirement in external:
        if canonicalize_name(requirement.name) in HOST_DISTRIBUTIONS:
            raise ValueError(
                f"{declarer and plugin_id_of(declarer)} declares forbidden host "
                f"dependency: {requirement}"
            )
    return {directory for name in local if (directory := plugin_id_of(name))}


def schedule(plugin_ids: Iterable[str]) -> list[str]:
    """Orders known-slow suites first; the remaining order is preserved."""
    return sorted(plugin_ids, key=lambda plugin_id: plugin_id not in SLOW_PLUGINS)


def _attempt(
    plugin_id: str, verify: Callable[[str], dict[str, object]], artifact_root: Path
) -> dict[str, object]:
    """Runs one plugin and converts its failure into a result entry.

    This is the per-plugin boundary: one failing suite must not stop the others.
    Every failure names a log: a failed command keeps its own output log, any
    other exception gets its full traceback in ``cases/<id>/failure.log``.
    """
    started = time.perf_counter()
    entry: dict[str, object]
    try:
        # The runner owns plugin/status; verify's fields cannot override them.
        entry = {**verify(plugin_id), "plugin": plugin_id, "status": "passed"}
    except Exception as error:
        if isinstance(error, CommandFailed):
            log = error.log
        else:
            log = case_directory(artifact_root, plugin_id) / "failure.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf-8")
        # Bare asserts in verify_plugin carry no message; fall back to the type name.
        lines = str(error).splitlines()
        entry = {
            "plugin": plugin_id,
            "status": "failed",
            "error": lines[0] if lines else type(error).__name__,
            "log": str(log),
        }
    entry["seconds"] = round(time.perf_counter() - started, 1)
    return entry


def write_results(artifact_root: Path, results: list[dict[str, object]]) -> None:
    """Replaces results.json atomically: readers only ever see a complete file.

    An interrupted write can leave a partial ``results.json.tmp`` behind, but
    ``results.json`` itself always holds the last complete result.
    """
    staging = artifact_root / "results.json.tmp"
    staging.write_text(json.dumps(results, indent=2), encoding="utf-8")
    os.replace(staging, artifact_root / "results.json")


def verify_all(
    plugin_ids: Iterable[str],
    verify: Callable[[str], dict[str, object]],
    *,
    artifact_root: Path,
    jobs: int,
) -> list[dict[str, object]]:
    """Verifies every plugin in a thread pool and returns entries sorted by plugin.

    ``results.json`` is rewritten from this (main) thread after each completion,
    so a run killed by a timeout still leaves the finished plugins' evidence; the
    write after the last completion is the complete result. It exists from the
    start, so an empty plugin selection still leaves a (empty) result file.
    """
    results: list[dict[str, object]] = []
    write_results(artifact_root, results)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [
            pool.submit(_attempt, plugin_id, verify, artifact_root)
            for plugin_id in schedule(plugin_ids)
        ]
        for future in as_completed(futures):
            entry = future.result()
            detail = entry.get("result") or entry.get("error")
            print(
                f"{entry['status']:<6} {entry['plugin']} {entry['seconds']}s: {detail}",
                flush=True,
            )
            results.append(entry)
            results.sort(key=lambda item: str(item["plugin"]))
            write_results(artifact_root, results)
    return results


def main(argv: list[str] | None = None) -> None:
    """Creates durable isolation evidence without modifying or installing from an editable checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plugins", nargs="+")
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="concurrent wheel builds and plugin verifications (default: CPU count)",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    artifact_root = (
        args.output or Path(tempfile.mkdtemp(prefix="shiori-plugin-isolation-"))
    ).resolve()
    if artifact_root.is_relative_to(REPOSITORY):
        raise ValueError("Isolation output must be outside the repository")
    artifact_root.mkdir(parents=True, exist_ok=True)
    wheelhouse = artifact_root / "wheels"
    wheelhouse.mkdir()
    plugin_ids = args.plugins or [
        path.name
        for path in sorted((REPOSITORY / "plugins").iterdir())
        if any((path / "tests").rglob("test_*.py"))
    ]
    for plugin_id in plugin_ids:
        if not (REPOSITORY / "plugins" / plugin_id / "pyproject.toml").is_file():
            raise ValueError(
                f"Tested plugin {plugin_id} must declare its package and test dependencies"
            )
    dependencies = plugin_dependencies(set(plugin_ids), extras=frozenset({"test"}))
    copies = {}
    for plugin_id in sorted(dependencies):
        copies[plugin_id] = artifact_root / "sources" / plugin_id
        stage_plugin_package(REPOSITORY / "plugins" / plugin_id, copies[plugin_id])
    wheels = build_wheels(
        {
            **copies,
            "sdk": REPOSITORY / "packages/sdk",
        },
        wheelhouse,
        artifact_root,
        jobs=args.jobs,
    )
    results = verify_all(
        plugin_ids,
        lambda plugin_id: verify_plugin(
            plugin_id,
            artifact_root=artifact_root,
            wheelhouse=wheelhouse,
            sources=copies,
            wheel=wheels[plugin_id],
        ),
        artifact_root=artifact_root,
        jobs=args.jobs,
    )
    failed = [entry for entry in results if entry["status"] == "failed"]
    if failed:
        print(f"{len(failed)} of {len(results)} plugin suites failed:", flush=True)
        for entry in failed:
            print(f"  {entry['plugin']}: {entry['log']}", flush=True)
        raise SystemExit(1)
    print(f"All {len(results)} plugin suites passed: {artifact_root}", flush=True)


if __name__ == "__main__":
    main()
