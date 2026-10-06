"""Offline construction of a private SenseVoice CPU interpreter."""

import shutil
import tarfile
from pathlib import Path
from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.child import private_environment, run_owned
from shiori_sdk.plugin_services import ServicePluginContext
from .runtime_manifest import CACHE_VARIABLES, OFFLINE_ENV, PYTHON_ARCHIVE


async def build_runtime(
    staging: Path,
    ctx: ServicePluginContext,
    root: Path,
    artifacts: tuple[Artifact, ...],
):
    """Build from fixed local resources with package resolution and network disabled."""
    with tarfile.open(staging / "downloads" / PYTHON_ARCHIVE) as archive:
        archive.extractall(staging, filter="data")
    interpreter = staging / "python/python.exe"
    if not interpreter.is_file():
        raise ValueError("独立 Python 包缺少 python.exe")
    env = private_environment(
        root, interpreter.parent, cache_variables=CACHE_VARIABLES, overrides=OFFLINE_ENV
    )
    packages = [item for item in artifacts if item.name.startswith("packages/")]
    bootstrap = [
        item
        for item in packages
        if Path(item.name).name.startswith(("setuptools-", "wheel-", "packaging-"))
    ]
    for label, selected in [("bootstrap", bootstrap), ("dependencies", packages)]:
        requirements = staging / (label + ".txt")
        requirements.write_text(
            "\n".join(
                (staging / "downloads" / item.name).as_uri()
                + " --hash=sha256:"
                + item.sha256
                for item in selected
            ),
            encoding="utf-8",
        )
        await run_owned(
            ctx.processes,
            [
                str(interpreter),
                "-I",
                "-X",
                "utf8",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-cache-dir",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--require-hashes",
                "-r",
                str(requirements),
            ],
            cwd=staging,
            env=env,
            log=root / "prepare.log",
        )
        requirements.unlink()
    shutil.move(staging / "downloads/models/sensevoice", staging / "model")
    shutil.move(staging / "downloads/models/fsmn-vad", staging / "vad")
    shutil.copyfile(
        Path(__file__).parent.parent / "runtime_assets/server.py",
        staging / "server.py",
    )
    await run_owned(
        ctx.processes,
        [
            str(interpreter),
            "-I",
            "-X",
            "utf8",
            "-c",
            "import torch, torchaudio, funasr; assert torch.version.cuda is None",
        ],
        cwd=staging,
        env=env,
        log=root / "prepare.log",
    )
    shutil.rmtree(staging / "downloads")
