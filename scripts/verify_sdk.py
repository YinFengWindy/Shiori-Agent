"""Install the SDK wheel without the host and execute its independent test suite."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from scripts.verify_plugin_tests import REPOSITORY, UV, build_wheel, run


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
    run(
        [UV, "pip", "install", "--python", str(python), f"{wheel}[testing]"],
        cwd=output,
        log=output / "install.log",
    )
    shutil.copytree(source / "tests", output / "tests")
    shutil.copyfile(source / "pyproject.toml", output / "pyproject.toml")
    expected = json.loads((source / "package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    probe = f"""
import importlib.util, json, sysconfig
from importlib.metadata import distribution, version, PackageNotFoundError
from pathlib import Path
import shiori_sdk
assert shiori_sdk.__version__ == version('shiori-sdk') == {expected!r}
assert shiori_sdk.RUNTIME_API_VERSION == {expected!r}
site = Path(sysconfig.get_paths()['purelib']).resolve()
assert Path(shiori_sdk.__file__).resolve().is_relative_to(site)
assert not json.loads(distribution('shiori-sdk').read_text('direct_url.json')).get('dir_info', {{}}).get('editable')
for name in ('agent', 'core', 'bus', 'bootstrap', 'desktop_bridge', 'shiori_plugin_testkit'):
    assert importlib.util.find_spec(name) is None, name
try:
    version('shiori-agent')
except PackageNotFoundError:
    pass
else:
    raise AssertionError('Host unexpectedly installed')
print('Independent wheel smoke passed:', shiori_sdk.__file__)
"""
    run([str(python), "-c", probe], cwd=output, log=output / "smoke.log")
    result = run(
        [str(python), "-m", "pytest", "-q"], cwd=output, log=output / "pytest.log"
    )
    print(result)
    print(f"SDK wheel evidence: {output}")


if __name__ == "__main__":
    main()
