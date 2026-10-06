"""Private v2ProPlus configuration and command construction."""

import json
from pathlib import Path
from shiori_sdk.managed.child import private_environment
from shiori_sdk.managed.paths import environment_path, native_path
from .runtime_manifest import CACHE_VARIABLES, OFFLINE_ENV, REQUIRED_FILES


def launch_runtime(installation: Path, port: int, token: str, root: Path):
    """Select fixed weights and loopback binding without changing external settings."""
    app = native_path(installation) / "app"
    root = native_path(root)
    config = root / "tts-config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "custom": {
                    "version": "v2ProPlus",
                    "device": "cuda",
                    "is_half": True,
                    "t2s_weights_path": environment_path(app / REQUIRED_FILES[3]),
                    "vits_weights_path": environment_path(app / REQUIRED_FILES[4]),
                    "bert_base_path": environment_path(
                        app
                        / "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
                    ),
                    "cnhuhbert_base_path": environment_path(
                        app / "GPT_SoVITS/pretrained_models/chinese-hubert-base"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    return (
        [
            environment_path(app / "runtime/python.exe"),
            "-I",
            "-X",
            "utf8",
            environment_path(app / "shiori_server.py"),
            str(port),
            token,
            environment_path(config),
        ],
        Path(environment_path(app)),
        private_environment(
            root,
            app / "runtime",
            cache_variables=CACHE_VARIABLES,
            overrides=OFFLINE_ENV,
        ),
    )
