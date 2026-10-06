"""Fixed resource identities for the private Windows CPU environment."""

import json
from pathlib import Path

from shiori_sdk.managed.artifacts import Artifact

REVISION = "sensevoice-cpu-20261006"
CACHE_VARIABLES = ("HF_HOME", "TORCH_HOME", "MODELSCOPE_CACHE", "NUMBA_CACHE_DIR")
OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
PYTHON_ARCHIVE = "cpython-3.12.15-windows.tar.gz"
PYTHON = Artifact(
    PYTHON_ARCHIVE,
    "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    22011023,
    "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402",
)


def resources() -> tuple[Artifact, ...]:
    """Load only package-shipped hash locks, never a caller-provided install manifest."""
    root = Path(__file__).parent
    models = json.loads((root / "models.lock.json").read_text(encoding="utf-8-sig"))
    packages = json.loads((root / "packages.lock.json").read_text(encoding="utf-8-sig"))
    return (
        PYTHON,
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
