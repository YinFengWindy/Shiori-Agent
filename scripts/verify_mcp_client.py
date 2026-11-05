"""Verify the internal MCP wheel without host imports or editable packages."""

from __future__ import annotations
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from scripts.commands import UV, run
from scripts.verify_plugin_tests import REPOSITORY, build_wheel, write_provenance_probe
from scripts.wheelhouse import install_from_wheelhouse


def main() -> None:
    """Build exact private wheels and exercise real stdio/HTTP outside the checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (
        args.output or Path(tempfile.mkdtemp(prefix="shiori-mcp-wheel-"))
    ).resolve()
    if output.is_relative_to(REPOSITORY):
        raise ValueError("Isolation output must be outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    wheels = output / "wheels"
    wheels.mkdir()
    source = REPOSITORY / "packages/mcp-client"
    for name, directory in (("sdk", REPOSITORY / "packages/sdk"), ("client", source)):
        build_wheel(directory, wheels, output / f"build-{name}.log")
    venv = output / "venv"
    run(
        [UV, "venv", "--python", sys.executable, str(venv)],
        cwd=output,
        log=output / "venv.log",
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install_from_wheelhouse(
        python,
        wheels,
        ["shiori-mcp-client[test]"],
        cwd=output,
        log=output / "install.log",
    )
    shutil.copytree(
        source / "tests",
        output / "tests",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    shutil.copyfile(source / "pyproject.toml", output / "pyproject.toml")
    write_provenance_probe(
        output,
        {"shiori_mcp_client": str(source / "src/shiori_mcp_client/__init__.py")},
        [],
        source_packages=[],
        wheelhouse=wheels,
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
    print(f"MCP client wheel evidence: {output}")


if __name__ == "__main__":
    main()
