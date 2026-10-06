"""Private v2ProPlus configuration and command construction."""

import json
from pathlib import Path
from shiori_sdk.managed.child import private_environment
from .runtime_manifest import CACHE_VARIABLES, OFFLINE_ENV, REQUIRED_FILES


def launch_runtime(installation: Path, port: int, token: str, root: Path):
    """Select fixed weights and loopback binding without changing external settings."""
    app = installation / "app"
    config = root / "tts-config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "custom": {
                    "version": "v2ProPlus",
                    "device": "cuda",
                    "is_half": True,
                    "t2s_weights_path": str(app / REQUIRED_FILES[3]),
                    "vits_weights_path": str(app / REQUIRED_FILES[4]),
                    "bert_base_path": str(
                        app
                        / "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
                    ),
                    "cnhuhbert_base_path": str(
                        app / "GPT_SoVITS/pretrained_models/chinese-hubert-base"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    return (
        [
            str(app / "runtime/python.exe"),
            "-I",
            "-X",
            "utf8",
            str(app / "shiori_server.py"),
            str(port),
            token,
            str(config),
        ],
        app,
        private_environment(
            root,
            app / "runtime",
            cache_variables=CACHE_VARIABLES,
            overrides=OFFLINE_ENV,
        ),
    )
