"""Exercise the copied probe against real external module/metadata trees and evasions."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import isolation_probe


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
    shutil.copyfile(isolation_probe.__file__, tmp_path / "probe.py")
    (tmp_path / "isolation.json").write_text(
        json.dumps(
            {
                "repository": str(tmp_path / "repository"),
                "host_roots": ["agent", "infra", "main"],
                "allowed_plugins": [],
                "modules": {},
                "source_packages": [str(tmp_path / "sources/demo")],
                "sdk_version": "3.0.0",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _audit(environment: Path, injection: str = "") -> subprocess.CompletedProcess[str]:
    # -I -S removes this repository's editable development environment entirely.
    source = f"""
import runpy, sys, sysconfig
from pathlib import Path
site = str(Path('site').resolve())
sys.path.insert(0, site)
sysconfig.get_paths = lambda: {{'purelib': site}}
probe = runpy.run_path('probe.py')
probe['pytest_sessionstart'](None)
{injection}
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


def test_execution_from_uninstalled_source_copy_is_rejected(environment: Path) -> None:
    source = environment / "sources/demo/backend/runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 42\n", encoding="utf-8")
    result = _audit(environment, "runpy.run_path('sources/demo/backend/runtime.py')")
    assert result.returncode != 0
    assert "source copy instead of installed wheel" in result.stderr
