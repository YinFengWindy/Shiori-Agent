"""Offline construction of a private SenseVoice CPU interpreter."""

import shutil
import tarfile
from pathlib import Path
from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.child import run_owned
from shiori_sdk.managed.paths import environment_path
from shiori_sdk.plugin_services import ServicePluginContext
from .runtime_manifest import PYTHON_ARCHIVE, PYTHON_RELATIVE
from .runtime_environment import runtime_environment
from .runtime_packages import install_packages


async def build_runtime(
    staging: Path,
    ctx: ServicePluginContext,
    root: Path,
    install_root: Path,
    artifacts: tuple[Artifact, ...],
):
    """Build from fixed local resources with package resolution and network disabled.

    Every resource is staged (downloaded or extracted from the bundle). Logs
    stay in the state ``root``; child temp/cache files go to ``install_root``.
    """
    with tarfile.open(staging / "downloads" / PYTHON_ARCHIVE) as archive:
        archive.extractall(staging, filter="data")
    (staging / "python").rename(staging / "p")
    interpreter = staging / PYTHON_RELATIVE
    if not interpreter.is_file():
        raise ValueError("独立 Python 包缺少 python.exe")
    await install_packages(staging, ctx, root, install_root, artifacts)
    env = runtime_environment(install_root, interpreter.parent)
    shutil.move(staging / "downloads/models/sensevoice", staging / "model")
    shutil.move(staging / "downloads/models/fsmn-vad", staging / "vad")
    shutil.copyfile(
        Path(__file__).parent.parent / "runtime_assets/server.py",
        staging / "server.py",
    )
    await run_owned(
        ctx.processes,
        [
            environment_path(interpreter),
            "-I",
            "-X",
            "utf8",
            "-c",
            "import torch, torchaudio, funasr, oss2; from Crypto.Cipher import AES; assert torch.version.cuda is None; assert AES.block_size == 16",
        ],
        cwd=Path(environment_path(staging)),
        env=env,
        log=root / "prepare.log",
    )
    shutil.rmtree(staging / "downloads")
