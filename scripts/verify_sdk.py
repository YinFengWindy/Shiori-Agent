"""Install the SDK wheel without the host and execute its independent test suite."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from scripts.verify_plugin_tests import (
    REPOSITORY,
    UV,
    build_wheel,
    run,
    write_provenance_probe,
)


def main() -> None:
    """Builds and tests the non-editable artifact in a repository-external directory."""
    output = Path(tempfile.mkdtemp(prefix="shiori-sdk-wheel-"))
    source = REPOSITORY / "packages/sdk"
    wheel = build_wheel(source, output, output / "build.log")
    venv = output / ".venv"
    run(
        [UV, "venv", "--python", sys.executable, str(venv)],
        cwd=output,
        log=output / "venv.log",
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # The base wheel's auto-loaded pytest entry must not require testing extras.
    run(
        [UV, "pip", "install", "--python", str(python), str(wheel), "pytest>=9.0"],
        cwd=output,
        log=output / "bare-install.log",
    )
    bare = output / "bare"
    bare.mkdir()
    (bare / "pytest.ini").write_text("[pytest]\naddopts = -W error\n", encoding="utf-8")
    (bare / "test_unrelated.py").write_text(
        "import importlib.util\nimport shiori_sdk\n\n"
        "def test_unrelated():\n"
        "    assert shiori_sdk.RUNTIME_API_VERSION == shiori_sdk.__version__\n"
        "    assert importlib.util.find_spec('pytest_asyncio') is None\n"
        "    assert importlib.util.find_spec('httpx') is not None\n",
        encoding="utf-8",
    )
    run(
        [str(python), "-m", "pytest", "--collect-only", "-q", "test_unrelated.py"],
        cwd=bare,
        log=output / "bare-collection.log",
    )
    run(
        [str(python), "-m", "pytest", "-q", "test_unrelated.py"],
        cwd=bare,
        log=output / "bare-pytest.log",
    )
    (bare / "test_requires_extra.py").write_text(
        "def test_requires_extra(sdk_context):\n    assert sdk_context\n",
        encoding="utf-8",
    )
    missing_extra = run(
        [str(python), "-m", "pytest", "-q", "test_requires_extra.py"],
        cwd=bare,
        log=output / "bare-missing-extra.log",
        expected=1,
    )
    assert "requires shiori-sdk[testing]" in missing_extra
    print("Base SDK + pytest: collection/run passed; missing testing extra diagnosed")
    run(
        [UV, "pip", "install", "--python", str(python), f"{wheel}[testing]"],
        cwd=output,
        log=output / "install.log",
    )
    shutil.copytree(source / "tests", output / "tests")
    shutil.copyfile(source / "pyproject.toml", output / "pyproject.toml")
    write_provenance_probe(output, {}, [])
    run(
        [str(python), "-c", "import verify_provenance; verify_provenance.audit()"],
        cwd=output,
        log=output / "smoke.log",
    )
    result = run(
        [
            str(python),
            "-m",
            "pytest",
            "-p",
            "verify_provenance",
            "--basetemp",
            str(output / "pytest-tmp"),
            "-q",
            "-W",
            "error",
            "tests",
        ],
        cwd=output,
        log=output / "pytest.log",
    )
    print(result)
    print(f"SDK wheel evidence: {output}")


if __name__ == "__main__":
    main()
