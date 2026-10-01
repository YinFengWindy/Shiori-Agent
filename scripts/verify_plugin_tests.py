"""Build private wheels and run every plugin in a separate repository-external venv."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
import traceback
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from shiori_sdk.testing.packages import stage_plugin_package

REPOSITORY = Path(__file__).resolve().parents[1]
UV = str(Path(sys.executable).with_name("uv.exe" if os.name == "nt" else "uv"))
if not Path(UV).is_file():
    UV = "uv"
# Measured as the longest suites in CI; starting them first shortens the pool's tail.
SDK_PLUGINS = frozenset({"citation", "context_pressure"})
SLOW_PLUGINS = ("telegram", "feishu", "qqbot")


class CommandFailed(RuntimeError):
    """An external command exited unexpectedly; ``log`` holds its complete output."""

    def __init__(self, message: str, *, log: Path) -> None:
        super().__init__(message)
        self.log = log


def clean_environment() -> dict[str, str]:
    """Drops import injection and service credentials before any external test process."""
    result = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "PYTEST"))
        and not any(
            word in key.upper()
            for word in (
                "API_KEY",
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "CREDENTIAL",
                "OPENAI",
            )
        )
    }
    result.update(PYTHONNOUSERSITE="1", PYTHONUTF8="1", UV_LINK_MODE="copy")
    return result


def run(command: list[str], *, cwd: Path, log: Path, expected: int = 0) -> str:
    """Records exact execution evidence and raises on unexpected test/install outcomes."""
    result = subprocess.run(
        command,
        cwd=cwd,
        env=clean_environment(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode != expected:
        raise CommandFailed(
            f"Expected exit {expected}, got {result.returncode}; see {log}\n{result.stdout[-6000:]}",
            log=log,
        )
    return result.stdout


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


def check_host_wheel(wheel: Path, log: Path) -> None:
    """Proves the runtime contains production APIs/assets and no host or plugin test trees."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    forbidden = (
        "tests/",
        "shiori_host_testing/",
        "plugins/",
        "agent/plugin_packages/",
        "data/",
        "logs/",
        "apps/desktop/",
    )
    for name in names:
        assert not name.startswith(forbidden), name
        assert "/tests/" not in name and "__pycache__" not in name, name
        assert not name.endswith((".pyc", ".kv.json", "plugin_config.json")), name
    assert "agent/provider.py" in names
    assert "shiori_runtime_resources/config/examples/config.example.toml" in names
    assert "shiori_runtime_resources/common_emojis.json" in names
    assert any(
        name.startswith("shiori_runtime_resources/skills/")
        and name.endswith("SKILL.md")
        for name in names
    )
    log.write_text("\n".join(names) + "\n", encoding="utf-8")


_PROVENANCE_CHECK = r"""
import hashlib, importlib.util, json, sys, sysconfig
from importlib.metadata import distributions
from pathlib import Path

source = Path(__SOURCE__)
plugin_id = __PLUGIN_ID__
allowed = set(__ALLOWED__)
site = Path(sysconfig.get_paths()["purelib"]).resolve()

def pytest_sessionfinish(session, exitstatus):
    paths = {}
    for name in ("agent.provider", "core.roles.store", "bus.event_bus", "bootstrap.paths", "desktop_bridge.service", "shiori_plugin_testkit.bridge", "shiori_host_testing.pytest_plugin", "shiori_sdk"):
        spec = importlib.util.find_spec(name)
        path = Path(spec.origin).resolve()
        assert path.is_relative_to(site), (name, path, site)
        paths[name] = str(path)
    spec = importlib.util.find_spec(f"plugins.{plugin_id}.backend.plugin")
    path = Path(spec.origin).resolve()
    assert path.is_relative_to(site), path
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256((source / "backend/plugin.py").read_bytes()).digest()
    paths[plugin_id] = str(path)
    installed = {dist.metadata["Name"] for dist in distributions() if dist.metadata["Name"].startswith("shiori-plugin-") and dist.metadata["Name"] != "shiori-plugin-testkit"}
    assert installed == allowed, (installed, allowed)
    for dist in distributions():
        direct = dist.read_text("direct_url.json")
        assert not direct or not json.loads(direct).get("dir_info", {}).get("editable"), dist.metadata["Name"]
    from bootstrap.paths import builtin_skills_path, common_emojis_path
    from bootstrap.init_workspace import CONFIG_TEMPLATE_PATH
    assert builtin_skills_path().is_relative_to(site)
    assert next(builtin_skills_path().glob("*/SKILL.md")).read_text(encoding="utf-8").strip()
    assert json.loads(common_emojis_path().read_text(encoding="utf-8"))
    assert CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    from bootstrap.init_workspace import init_workspace
    workspace = Path("resource-workspace").resolve()
    init_workspace(config_path=workspace / "config.toml", workspace=workspace)
    assert (workspace / "config.toml").read_bytes() == CONFIG_TEMPLATE_PATH.read_bytes()
    Path("provenance.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")
"""


_SDK_PROVENANCE_CHECK = r"""
import hashlib, importlib.util, json, sys, sysconfig
from importlib.metadata import distributions, version
from pathlib import Path
source = Path(__SOURCE__)
plugin_id = __PLUGIN_ID__
allowed = set(__ALLOWED__)
site = Path(sysconfig.get_paths()["purelib"]).resolve()
def pytest_sessionfinish(session, exitstatus):
    installed = {dist.metadata["Name"] for dist in distributions()}
    assert "shiori-agent" not in installed and "shiori-plugin-testkit" not in installed and "shiori-host-testing" not in installed, installed
    assert installed.intersection({"shiori-plugin-" + name.replace("_", "-") for name in ("default_memory",)}) <= allowed
    for name in ("agent", "bootstrap", "core", "bus", "desktop_bridge", "memory2", "shiori_host_testing"):
        assert importlib.util.find_spec(name) is None, name
    paths = {}
    for name in ("shiori_sdk", "shiori_sdk.testing", f"plugins.{plugin_id}.backend.plugin"):
        path = Path(importlib.util.find_spec(name).origin).resolve()
        assert path.is_relative_to(site), (name, path)
        paths[name] = str(path)
    plugin_path = Path(paths[f"plugins.{plugin_id}.backend.plugin"])
    assert hashlib.sha256(plugin_path.read_bytes()).digest() == hashlib.sha256((source / "backend/plugin.py").read_bytes()).digest()
    for dist in distributions():
        direct = dist.read_text("direct_url.json")
        assert not direct or not json.loads(direct).get("dir_info", {}).get("editable"), dist.metadata["Name"]
    assert {name for name in installed if name.startswith("shiori-plugin-")} == allowed
    paths["sdk_version"] = version("shiori-sdk")
    Path("provenance.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")
"""


def case_directory(artifact_root: Path, plugin_id: str) -> Path:
    """Holds every piece of per-plugin evidence (venv, logs, provenance)."""
    return artifact_root / "cases" / plugin_id


def verify_plugin(
    plugin_id: str,
    *,
    artifact_root: Path,
    wheelhouse: Path,
    source: Path,
    host: Path | None,
    kit: Path | None,
    wheel: Path,
) -> dict[str, object]:
    """Runs all target tests with only the target and its declared sibling dependencies installed."""
    case = case_directory(artifact_root, plugin_id)
    case.mkdir(parents=True)
    venv = case / "venv"
    run(
        [UV, "venv", "--python", sys.executable, str(venv)],
        cwd=case,
        log=case / "venv.log",
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        [
            UV,
            "pip",
            "install",
            "--python",
            str(python),
            "--find-links",
            str(wheelhouse),
            *([str(host), str(kit)] if host is not None else []),
            f"{wheel}[test]",
        ],
        cwd=case,
        log=case / "install.log",
    )
    ids = plugin_dependencies(
        {plugin_id}, extras=frozenset({"test"}), include_host=host is not None
    )
    allowed = ["shiori-plugin-" + name.replace("_", "-") for name in sorted(ids)]
    check = (
        (_PROVENANCE_CHECK if host is not None else _SDK_PROVENANCE_CHECK)
        .replace("__SOURCE__", repr(str(source)))
        .replace("__PLUGIN_ID__", repr(plugin_id))
        .replace("__ALLOWED__", repr(allowed))
    )
    (case / "verify_provenance.py").write_text(check, encoding="utf-8")
    output = run(
        [
            str(python),
            "-m",
            "pytest",
            "-p",
            "verify_provenance",
            "-c",
            str(source / "pyproject.toml"),
            str(source / "tests"),
            "-q",
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
            "-c",
            str(source / "pyproject.toml"),
            str(probe),
            "-q",
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
    include_host: bool = True,
) -> set[str]:
    """Resolves selected extras and declared sibling dependencies for this interpreter.

    Runtime requirements always apply. Each requested extra adds its own optional
    requirements; siblings receive only extras explicitly requested on their edge.
    The independently built testkit is a foundation package, not a plugin directory.
    """
    resolved: set[str] = set()
    visited: set[tuple[str, str]] = set()
    pending = [("default_memory", "")] if include_host else []
    for plugin_id in plugin_ids:
        pending.append((plugin_id, ""))
        pending.extend((plugin_id, canonicalize_name(extra)) for extra in extras)
    while pending:
        plugin_id, extra = pending.pop()
        if (plugin_id, extra) in visited:
            continue
        visited.add((plugin_id, extra))
        project = tomllib.loads(
            (REPOSITORY / "plugins" / plugin_id / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )["project"]
        resolved.add(plugin_id)
        requirements = list(project.get("dependencies", []))
        # Optional groups are evaluated in their own active extra context. Runtime
        # requirements also get the base context, matching normal package installs.
        for group, optional in project.get("optional-dependencies", {}).items():
            if extra and canonicalize_name(group) == extra:
                requirements.extend(optional)
        for raw_requirement in requirements:
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate({"extra": extra}):
                continue
            name = canonicalize_name(requirement.name)
            if name == "shiori-plugin-testkit" or not name.startswith("shiori-plugin-"):
                continue
            sibling = name.removeprefix("shiori-plugin-").replace("-", "_")
            pending.append((sibling, ""))
            pending.extend(
                (sibling, canonicalize_name(selected))
                for selected in requirement.extras
            )
    return resolved


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
        "--sdk-only",
        action="store_true",
        help="Run migrated plugins without installing the host",
    )
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
    plugin_ids = args.plugins or (
        sorted(SDK_PLUGINS)
        if args.sdk_only
        else [
            path.name
            for path in sorted((REPOSITORY / "plugins").iterdir())
            if any((path / "tests").rglob("test_*.py"))
        ]
    )
    if args.sdk_only and not set(plugin_ids) <= SDK_PLUGINS:
        raise ValueError("SDK isolation only accepts migrated plugins")
    for plugin_id in plugin_ids:
        if not (REPOSITORY / "plugins" / plugin_id / "pyproject.toml").is_file():
            raise ValueError(
                f"Tested plugin {plugin_id} must declare its package and test dependencies"
            )
    needs_host = bool(set(plugin_ids) - SDK_PLUGINS)
    dependencies = plugin_dependencies(
        set(plugin_ids), extras=frozenset({"test"}), include_host=needs_host
    )
    copies = {}
    for plugin_id in sorted(dependencies):
        copies[plugin_id] = artifact_root / "sources" / plugin_id
        stage_plugin_package(REPOSITORY / "plugins" / plugin_id, copies[plugin_id])
    wheels = build_wheels(
        {
            **copies,
            "sdk": REPOSITORY / "packages/sdk",
            **(
                {
                    "host": REPOSITORY,
                    "testkit": REPOSITORY / "packages/shiori-plugin-testkit",
                    "host-testing": REPOSITORY / "packages/shiori-host-testing",
                }
                if needs_host
                else {}
            ),
        },
        wheelhouse,
        artifact_root,
        jobs=args.jobs,
    )
    host, kit = wheels.get("host"), wheels.get("testkit")
    if host is not None:
        check_host_wheel(host, artifact_root / "host-wheel-files.txt")
    results = verify_all(
        plugin_ids,
        lambda plugin_id: verify_plugin(
            plugin_id,
            artifact_root=artifact_root,
            wheelhouse=wheelhouse,
            source=copies[plugin_id],
            host=host if plugin_id not in SDK_PLUGINS else None,
            kit=kit if plugin_id not in SDK_PLUGINS else None,
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
