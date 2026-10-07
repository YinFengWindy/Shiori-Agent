"""Fixed resource identities for the private Windows CPU environment."""

import json
from pathlib import Path

from shiori_sdk.managed.artifacts import Artifact

REVISION = "sensevoice-cpu-20261006"
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "UV_PYTHON_DOWNLOADS": "never",
    "UV_NO_PROGRESS": "1",
    "OMP_NUM_THREADS": "4",
    "MKL_NUM_THREADS": "4",
}
PYTHON_ARCHIVE = "cpython-3.12.15-windows.tar.gz"
PYTHON_RELATIVE = "p/python.exe"
UV_ARCHIVE = "uv-0.12.23-windows-x64.zip"
SOURCE_PACKAGES = ("antlr4-python3-runtime", "crcmod", "jieba", "oss2")
# Bytes of one prepared version. Measured from the locks: unpacked wheels
# 1,740,387,379 + source package trees 41,042,772 + Python 63,230,869 + models
# 938,413,143 = 2,783,074,163; rounded up for bytecode caches written by the
# import check and per-file cluster slack.
INSTALLED_SIZE = 3_200_000_000
PYTHON = Artifact(
    PYTHON_ARCHIVE,
    "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    22011023,
    "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402",
)
UV = Artifact(
    UV_ARCHIVE,
    "https://github.com/astral-sh/uv/releases/download/0.12.23/uv-x86_64-pc-windows-msvc.zip",
    18043715,
    "75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90",
)


def resources() -> tuple[Artifact, ...]:
    """Load only package-shipped hash locks, never a caller-provided install manifest."""
    root = Path(__file__).parent
    models = json.loads((root / "models.lock.json").read_text(encoding="utf-8-sig"))
    packages = json.loads((root / "packages.lock.json").read_text(encoding="utf-8-sig"))
    return (
        PYTHON,
        UV,
        *(Artifact(**item) for item in models),
        *(
            Artifact(
                "packages/" + item["filename"],
                item["url"],
                item["size"],
                item["sha256"],
            )
            for item in packages
        ),
    )
