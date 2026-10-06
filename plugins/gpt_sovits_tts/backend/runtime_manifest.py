"""Fixed official Windows artifacts and required v2ProPlus model paths."""

from shiori_sdk.managed.artifacts import Artifact

REVISION = "v2pro-20261005"
CACHE_VARIABLES = ("HF_HOME", "TORCH_HOME", "CUDA_CACHE_PATH", "MODELSCOPE_CACHE")
OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
ARCHIVE = "GPT-SoVITS-v2pro-20261005.7z"
PACKAGE_ROOT = "GPT-SoVITS-v2pro-20260620"
ARTIFACTS = (
    Artifact(
        ARCHIVE,
        "https://huggingface.co/lj1995/GPT-SoVITS-windows-package/resolve/3146eac7da3723f60012b8633bdd5d61b7769e2a/"
        + ARCHIVE,
        10832887120,
        "aede806030b25d2a69420acb64e657f5ec46c010fba8576042e51a141c3f64d3",
    ),
    Artifact(
        "7zr.exe",
        "https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe",
        602624,
        "256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282",
    ),
)
REQUIRED_FILES = (
    "runtime/python.exe",
    "api_v2.py",
    "runtime/ffmpeg.exe",
    "GPT_SoVITS/pretrained_models/s1v3.ckpt",
    "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth",
    "GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt",
    "GPT_SoVITS/pretrained_models/chinese-hubert-base/pytorch_model.bin",
    "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "GPT_SoVITS/text/G2PWModel/g2pW.onnx",
)
