"""Private short cache paths keep third-party CPU tooling within Windows limits."""

from pathlib import Path

from shiori_sdk.managed.child import private_environment
from shiori_sdk.managed.paths import environment_path, native_path

from .runtime_manifest import OFFLINE_ENV


def runtime_environment(root: Path, executables: Path) -> dict[str, str]:
    """Use only this provider's private directories; never inherit uv settings."""
    env = private_environment(root, executables, overrides=OFFLINE_ENV)
    for key in tuple(env):
        if key.startswith("UV_") and key not in OFFLINE_ENV:
            del env[key]
    for key, name in {
        "TEMP": "t",
        "TMP": "t",
        "UV_CACHE_DIR": "u",
        "HF_HOME": "hf",
        "MODELSCOPE_CACHE": "ms",
        "TORCH_HOME": "th",
        "NUMBA_CACHE_DIR": "nb",
    }.items():
        path = native_path(root / name)
        path.mkdir(parents=True, exist_ok=True)
        env[key] = environment_path(path)
    return env
