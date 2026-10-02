"""Build the actual host API and its production resources without development trees."""

import shutil
from pathlib import Path

from setuptools import find_namespace_packages, setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
HOST_PACKAGES = (
    "agent",
    "bootstrap",
    "bus",
    "conversation",
    "core",
    "desktop_bridge",
    "infra",
    "proactive_v2",
    "prompts",
    "session",
    "utils",
    "shiori_runtime_resources",
)


class BuildRuntime(build_py):
    """Adds the same skills and emoji assets used by the frozen application plus setup's template."""

    def run(self):
        super().run()
        destination = Path(self.build_lib) / "shiori_runtime_resources"
        shutil.copytree(
            ROOT / "apps/backend/skills",
            destination / "skills",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        template = destination / "config/examples/config.example.toml"
        template.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "config/examples/config.example.toml", template)
        shutil.copyfile(
            ROOT / "apps/desktop/renderer/src/chat/common_emojis.json",
            destination / "common_emojis.json",
        )


requirements = [
    line.strip()
    for line in (ROOT / "apps/backend/requirements/production.txt")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip() and not line.startswith("#")
]
setup(
    packages=[
        name
        for name in find_namespace_packages(
            where="apps/backend",
            include=[
                pattern for name in HOST_PACKAGES for pattern in (name, f"{name}.*")
            ],
            exclude=[
                "*.tests",
                "*.tests.*",
                "*.__pycache__",
                "*.__pycache__.*",
                "agent.plugin_packages",
                "agent.plugin_packages.*",
            ],
        )
        if any((ROOT / "apps/backend" / name.replace(".", "/")).glob("*.py"))
    ],
    package_dir={"": "apps/backend"},
    include_package_data=False,
    install_requires=[
        *requirements,
        "shiori-sdk==3.1.0",
        "shiori-plugin-default-memory==0.1.0",
    ],
    cmdclass={"build_py": BuildRuntime},
)
