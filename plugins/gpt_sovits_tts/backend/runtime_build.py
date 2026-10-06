"""Provider-specific preparation of the fixed GPT-SoVITS Windows package."""

import shutil
from pathlib import Path
from shiori_sdk.managed.child import private_environment, run_owned
from shiori_sdk.plugin_services import ServicePluginContext
from .runtime_manifest import (
    CACHE_VARIABLES,
    OFFLINE_ENV,
    ARCHIVE,
    PACKAGE_ROOT,
    REQUIRED_FILES,
)


async def build_runtime(staging: Path, ctx: ServicePluginContext, root: Path):
    """Extract only a verified archive and check its private CUDA interpreter."""
    env = private_environment(
        root,
        staging / "downloads",
        cache_variables=CACHE_VARIABLES,
        overrides=OFFLINE_ENV,
    )
    await run_owned(
        ctx.processes,
        [
            str(staging / "downloads/7zr.exe"),
            "x",
            str(staging / "downloads" / ARCHIVE),
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
            str(app / "runtime/python.exe"),
            "-I",
            "-X",
            "utf8",
            "-c",
            "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; assert torch.cuda.get_device_properties(0).total_memory > 0",
        ],
        cwd=app,
        env=private_environment(
            root,
            app / "runtime",
            cache_variables=CACHE_VARIABLES,
            overrides=OFFLINE_ENV,
        ),
        log=root / "prepare.log",
    )
    # The verified source package is not needed after its completed extraction.
    shutil.rmtree(staging / "downloads")
