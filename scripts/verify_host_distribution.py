"""Verify the private host wheel and production resources independently of plugin tests."""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

from scripts.verify_plugin_tests import REPOSITORY, UV, build_wheels, run


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


_RESOURCE_PROBE = r"""
import importlib.util, json, sysconfig
from importlib.metadata import distributions
from pathlib import Path
site = Path(sysconfig.get_paths()["purelib"]).resolve()
paths = {}
for name in ("agent.provider", "core.roles.store", "bus.event_bus", "bootstrap.paths", "desktop_bridge.service", "shiori_sdk", "plugins.default_memory.backend.plugin"):
    path = Path(importlib.util.find_spec(name).origin).resolve()
    assert path.is_relative_to(site), (name, path)
    paths[name] = str(path)
assert importlib.util.find_spec("shiori_host_testing") is None
assert importlib.util.find_spec("tests") is None
installed = {dist.metadata["Name"] for dist in distributions()}
assert {name for name in installed if name.startswith("shiori-plugin-")} == {"shiori-plugin-default-memory"}
for dist in distributions():
    direct = dist.read_text("direct_url.json")
    assert not direct or not json.loads(direct).get("dir_info", {}).get("editable"), dist.metadata["Name"]
from bootstrap.paths import builtin_skills_path, common_emojis_path
from bootstrap.init_workspace import CONFIG_TEMPLATE_PATH, init_workspace
assert builtin_skills_path().is_relative_to(site)
assert next(builtin_skills_path().glob("*/SKILL.md")).read_text(encoding="utf-8").strip()
assert json.loads(common_emojis_path().read_text(encoding="utf-8"))
assert CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
workspace = Path("resource-workspace").resolve()
init_workspace(config_path=workspace / "config.toml", workspace=workspace)
assert (workspace / "config.toml").read_bytes() == CONFIG_TEMPLATE_PATH.read_bytes()
Path("provenance.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")
print("Installed host modules and production resources passed")
"""


def main() -> None:
    """Build host dependencies and exercise their installed, non-editable resource paths."""
    output = Path(tempfile.mkdtemp(prefix="shiori-host-wheel-"))
    wheels = build_wheels(
        {
            "host": REPOSITORY,
            "sdk": REPOSITORY / "packages/sdk",
            "default_memory": REPOSITORY / "plugins/default_memory",
        },
        output,
        output,
        jobs=3,
    )
    check_host_wheel(wheels["host"], output / "host-wheel-files.txt")
    venv = output / ".venv"
    run(
        [UV, "venv", "--python", sys.executable, str(venv)],
        cwd=output,
        log=output / "venv.log",
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
            str(output),
            str(wheels["host"]),
        ],
        cwd=output,
        log=output / "install.log",
    )
    run([str(python), "-c", _RESOURCE_PROBE], cwd=output, log=output / "resources.log")
    print(f"Host wheel/resource evidence: {output}")


if __name__ == "__main__":
    main()
