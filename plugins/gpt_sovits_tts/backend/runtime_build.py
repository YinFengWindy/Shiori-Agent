"""Provider-specific preparation of the fixed GPT-SoVITS Windows package."""

import shutil
from collections.abc import Mapping
from pathlib import Path
from shiori_sdk.managed.child import private_environment, run_owned
from shiori_sdk.managed.paths import environment_path
from shiori_sdk.plugin_services import ServicePluginContext
from .runtime_manifest import (
    CACHE_VARIABLES,
    OFFLINE_ENV,
    ARCHIVE,
    PACKAGE_ROOT,
    REQUIRED_FILES,
)


async def build_runtime(
    staging: Path,
    resources: Mapping[str, Path],
    ctx: ServicePluginContext,
    root: Path,
    install_root: Path,
):
    """Extract only a verified archive and check its private CUDA interpreter.

    The archive is read where it is: in the download cache link, or the
    user's imported original, which is never copied. Logs stay in the state
    ``root``; child temp/cache files go to ``install_root``.
    """
    tool = resources["7zr.exe"]
    env = private_environment(
        install_root,
        tool.parent,
        cache_variables=CACHE_VARIABLES,
        overrides=OFFLINE_ENV,
    )
    await run_owned(
        ctx.processes,
        [
            str(tool),
            "x",
            str(resources[ARCHIVE]),
            "-o" + str(staging / "unpacked"),
            "-y",
        ],
        cwd=staging,
        env=env,
        log=root / "prepare.log",
    )
    app = staging / "app"
    (staging / "unpacked" / PACKAGE_ROOT).rename(app)
    (staging / "unpacked").rmdir()
    for name in REQUIRED_FILES:
        path = app / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"整合包缺少必要文件：{name}")
    shutil.copyfile(
        Path(__file__).parent.parent / "runtime_assets/server.py",
        app / "shiori_server.py",
    )
    await run_owned(
        ctx.processes,
        [
            environment_path(app / "runtime/python.exe"),
            "-I",
            "-X",
            "utf8",
            "-c",
            "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; assert torch.cuda.get_device_properties(0).total_memory > 0",
        ],
        cwd=Path(environment_path(app)),
        env=private_environment(
            install_root,
            app / "runtime",
            cache_variables=CACHE_VARIABLES,
            overrides=OFFLINE_ENV,
        ),
        log=root / "prepare.log",
    )
    # The staged sources (7zr.exe always, the archive unless imported in place)
    # are not needed after the completed extraction.
    shutil.rmtree(staging / "downloads")
