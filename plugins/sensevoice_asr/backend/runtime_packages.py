"""Install the fixed CPU dependency lock with a pinned, offline Windows installer."""

import json
import shutil
import zipfile
from pathlib import Path

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.child import run_owned
from shiori_sdk.managed.paths import environment_path, native_path
from shiori_sdk.plugin_services import ServicePluginContext

from .runtime_environment import runtime_environment
from .runtime_manifest import PYTHON_RELATIVE, SOURCE_PACKAGES, UV_ARCHIVE


async def install_packages(
    staging: Path,
    ctx: ServicePluginContext,
    root: Path,
    artifacts: tuple[Artifact, ...],
):
    """Build only locked sources with standard backend options and no online resolution."""
    uv = staging / "uv.exe"
    with zipfile.ZipFile(staging / "downloads" / UV_ARCHIVE) as archive:
        with archive.open("uv.exe") as source, uv.open("wb") as destination:
            shutil.copyfileobj(source, destination)
    interpreter = staging / PYTHON_RELATIVE
    env = runtime_environment(root, interpreter.parent)
    command = [
        environment_path(uv),
        "--no-config",
        "pip",
        "install",
        "--python",
        environment_path(interpreter),
        "--offline",
        "--no-index",
        "--no-deps",
        "--no-build-isolation",
        "--require-hashes",
    ]
    bdist = native_path(root / "b")
    if bdist.exists():
        shutil.rmtree(bdist)
    for index, name in enumerate(SOURCE_PACKAGES):
        # setuptools parses this value with shlex. Normal short paths avoid its
        # legacy relative-dot joins without changing any upstream source content.
        location = Path(environment_path(bdist / str(index))).as_posix()
        option = (
            name
            + ":--build-option=--bdist-dir="
            + json.dumps(location, ensure_ascii=False)
        )
        command.extend(["--config-settings-package", option])
    packages = [item for item in artifacts if item.name.startswith("packages/")]
    bootstrap = [
        item
        for item in packages
        if Path(item.name).name.startswith(("setuptools-", "wheel-", "packaging-"))
    ]
    try:
        for label, selected in [("bootstrap", bootstrap), ("dependencies", packages)]:
            requirements = staging / (label + ".txt")
            requirements.write_text(
                "\n".join(
                    (Path("downloads") / item.name).as_posix()
                    + " --hash=sha256:"
                    + item.sha256
                    for item in selected
                ),
                encoding="utf-8",
            )
            await run_owned(
                ctx.processes,
                [*command, "-r", environment_path(requirements)],
                cwd=Path(environment_path(staging)),
                env=env,
                log=root / "prepare.log",
            )
            requirements.unlink()
        await run_owned(
            ctx.processes,
            [
                environment_path(uv),
                "--no-config",
                "pip",
                "check",
                "--python",
                environment_path(interpreter),
            ],
            cwd=Path(environment_path(staging)),
            env=env,
            log=root / "prepare.log",
        )
    finally:
        if bdist.exists():
            shutil.rmtree(bdist)
    uv.unlink()
