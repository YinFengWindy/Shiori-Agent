"""Executed only by the private verified GPT-SoVITS interpreter."""

# pyright: reportMissingImports=false

import os
from pathlib import Path
import runpy
import sys


def main():
    """Validate actual GPU configuration before exposing this generation's identity."""
    port, token, config = sys.argv[1:]
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    import torch
    import uvicorn

    if not torch.cuda.is_available():
        raise RuntimeError("GPT-SoVITS 托管环境需要可用的 NVIDIA CUDA 显卡")
    sys.argv = ["api_v2.py", "-a", "127.0.0.1", "-p", port, "-c", config]
    module = runpy.run_path(str(root / "api_v2.py"), run_name="shiori_managed")
    actual = module["tts_pipeline"].configs
    if str(actual.device) != "cuda" or actual.version != "v2ProPlus":
        raise RuntimeError("GPT-SoVITS 实际加载的模型或设备与托管配置不符")
    app = module["APP"]

    @app.get("/shiori-runtime")
    async def identity():
        return {"token": token}

    uvicorn.run(app, host="127.0.0.1", port=int(port), workers=1)


if __name__ == "__main__":
    main()
