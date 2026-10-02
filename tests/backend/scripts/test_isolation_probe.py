"""Exercise the copied probe against real external module/metadata trees and evasions."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from scripts import isolation_probe
from scripts.sdk_boundaries import (
    HOST_DISTRIBUTIONS,
    LOCAL_DISTRIBUTION_PREFIX,
    PLUGIN_DISTRIBUTION_PREFIX,
)


def _wheel_origin(wheel: Path) -> str:
    return json.dumps({"url": wheel.as_uri(), "archive_info": {}})


@pytest.fixture
def environment(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "shiori_sdk/testing").mkdir(parents=True)
    (site / "shiori_sdk/__init__.py").write_text(
        "__version__ = RUNTIME_API_VERSION = '3.0.0'\n", encoding="utf-8"
    )
    (site / "shiori_sdk/testing/__init__.py").touch()
    metadata = site / "shiori_sdk-3.0.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Name: shiori-sdk\nVersion: 3.0.0\n", encoding="utf-8"
    )
    # The installed tree mirrors a real wheel in the wheelhouse byte for byte.
    files = ["shiori_sdk/__init__.py", "shiori_sdk/testing/__init__.py"]
    (metadata / "RECORD").write_text(
        "".join(f"{name},,\n" for name in [*files, f"{metadata.name}/METADATA"]),
        encoding="utf-8",
    )
    wheel = tmp_path / "wheels/shiori_sdk-3.0.0-py3-none-any.whl"
    wheel.parent.mkdir()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in [*files, f"{metadata.name}/METADATA"]:
            archive.write(site / name, name)
        archive.writestr(f"{metadata.name}/RECORD", "")
    (metadata / "direct_url.json").write_text(_wheel_origin(wheel), encoding="utf-8")
    shutil.copyfile(isolation_probe.__file__, tmp_path / "probe.py")
    (tmp_path / "isolation.json").write_text(
        json.dumps(
            {
                "repository": str(tmp_path / "repository"),
                "host_roots": ["agent", "infra", "main"],
                "allowed_plugins": [],
                "modules": {},
                "source_packages": [
                    str(tmp_path / "sources/demo"),
                    str(tmp_path / "sources/sibling"),
                ],
                "sdk_version": "3.0.0",
                "wheelhouse": str(tmp_path / "wheels"),
                "local_prefix": LOCAL_DISTRIBUTION_PREFIX,
                "plugin_prefix": PLUGIN_DISTRIBUTION_PREFIX,
                "host_distributions": sorted(HOST_DISTRIBUTIONS),
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _audit(
    environment: Path, injection: str = "", *, before_session: bool = False
) -> subprocess.CompletedProcess[str]:
    # -I -S removes this repository's editable development environment entirely.
    source = f"""
import runpy, sys, sysconfig
from pathlib import Path
site = str(Path('site').resolve())
sys.path.insert(0, site)
sysconfig.get_paths = lambda: {{'purelib': site}}
probe = runpy.run_path('probe.py')
probe['pytest_load_initial_conftests'](None, None, None)
{injection if before_session else ""}
probe['pytest_sessionstart'](None)
{injection if not before_session else ""}
probe['audit']()
"""
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c", source],
        cwd=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_valid_external_environment_records_installed_sources(
    environment: Path,
) -> None:
    result = _audit(environment)
    assert result.returncode == 0, result.stderr
    evidence = json.loads((environment / "provenance.json").read_text(encoding="utf-8"))
    assert evidence["distributions"] == {"shiori-sdk": "3.0.0"}
    assert evidence["absent_host_roots"] == ["agent", "infra", "main"]
    assert evidence["repository_path_injection"] is False


@pytest.mark.parametrize(
    "injection",
    [
        "sys.path.append(str(Path('repository').resolve()))",
        "import types; sys.modules['agent'] = types.ModuleType('agent')",
        "Path(site, 'infra.py').touch()",
        "Path(site, 'main.py').touch()",
        "import types; m = types.ModuleType('hidden'); m.__file__ = str(Path('repository/hidden.py').resolve()); sys.modules['hidden'] = m",
    ],
)
def test_repository_or_host_injection_fails(environment: Path, injection: str) -> None:
    assert _audit(environment, injection).returncode != 0


@pytest.mark.parametrize(
    "name,extra",
    [
        ("shiori-sdk", '{"dir_info": {"editable": true}}'),
        ("shiori-agent", "{}"),
        ("shiori-host-testing", "{}"),
        ("shiori-plugin-default-memory", "{}"),
        ("shiori-plugin-undeclared", "{}"),
    ],
)
def test_unexpected_or_editable_distributions_fail(
    environment: Path, name: str, extra: str
) -> None:
    metadata = environment / "site" / f"{name.replace('-', '_')}-3.0.0.dist-info"
    metadata.mkdir(exist_ok=True)
    (metadata / "METADATA").write_text(
        f"Name: {name}\nVersion: 3.0.0\n", encoding="utf-8"
    )
    (metadata / "direct_url.json").write_text(extra, encoding="utf-8")
    assert _audit(environment).returncode != 0


@pytest.mark.parametrize(
    "origin",
    [
        # An index install records no direct URL at all.
        None,
        json.dumps({"url": "file:///elsewhere/shiori_sdk-3.0.0-py3-none-any.whl"}),
        json.dumps({"url": "https://example.invalid/shiori_sdk-3.0.0.whl"}),
    ],
    ids=["index", "outside-wheelhouse", "remote-url"],
)
def test_shiori_distribution_not_installed_from_the_wheelhouse_fails(
    environment: Path, origin: str | None
) -> None:
    direct = environment / "site/shiori_sdk-3.0.0.dist-info/direct_url.json"
    if origin is None:
        direct.unlink()
    else:
        direct.write_text(origin, encoding="utf-8")
    assert _audit(environment).returncode != 0


@pytest.mark.parametrize(
    "stale",
    [
        # A cached older build of the same version replaced a module's content.
        "shiori_sdk/testing/__init__.py",
        # A cached older build still ships a module the wheelhouse wheel dropped.
        "shiori_sdk/testing/removed.py",
    ],
    ids=["changed-content", "extra-file"],
)
def test_same_version_content_differing_from_the_wheelhouse_wheel_fails(
    environment: Path, stale: str
) -> None:
    (environment / "site" / stale).write_text("OLD = True\n", encoding="utf-8")
    record = environment / "site/shiori_sdk-3.0.0.dist-info/RECORD"
    if stale.endswith("removed.py"):
        with record.open("a", encoding="utf-8") as stream:
            stream.write(f"{stale},,\n")
    result = _audit(environment)
    assert result.returncode != 0
    assert "differs from wheelhouse wheel" in result.stderr


def test_execution_from_uninstalled_source_copy_is_rejected(environment: Path) -> None:
    source = environment / "sources/demo/backend/runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 42\n", encoding="utf-8")
    result = _audit(environment, "runpy.run_path('sources/demo/backend/runtime.py')")
    assert result.returncode != 0
    assert "source copy instead of installed wheel" in result.stderr


@pytest.mark.parametrize(
    "relative,diagnostic",
    [
        (
            "sources/sibling/backend/runtime.py",
            "source copy instead of installed wheel",
        ),
        ("sources/sibling/testing/helper.py", "source copy instead of installed wheel"),
        (
            "repository/packages/sdk/python/shiori_sdk/helper.py",
            "Repository implementation executed",
        ),
    ],
)
def test_temporary_sibling_or_sdk_alias_is_rejected_before_it_can_be_removed(
    environment: Path, relative: str, diagnostic: str
) -> None:
    source = environment / relative
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 42\n", encoding="utf-8")
    result = _audit(
        environment,
        f"""
import importlib.util
spec = importlib.util.spec_from_file_location('temporary_alias', {relative!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
try:
    spec.loader.exec_module(module)
finally:
    del sys.modules[spec.name]
""",
        before_session=True,
    )
    assert result.returncode != 0
    assert diagnostic in result.stderr


def test_external_sibling_tests_remain_executable(environment: Path) -> None:
    source = environment / "sources/sibling/tests/test_demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 42\n", encoding="utf-8")
    assert (
        _audit(
            environment, "runpy.run_path('sources/sibling/tests/test_demo.py')"
        ).returncode
        == 0
    )
