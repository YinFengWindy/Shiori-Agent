"""Final-version paths retain long-path support in both Python and model configuration."""

import json
from pathlib import Path

from shiori_sdk.managed.paths import environment_path, native_path
from plugins.gpt_sovits_tts.backend.runtime_launch import launch_runtime


def test_final_runtime_launch_uses_native_model_script_and_executable_paths(tmp_path):
    root = tmp_path / "workspace/plugin-data/gpt_sovits_tts/runtime"
    installation = root / "versions" / ("complete-environment-" * 5)
    command, cwd, environment = launch_runtime(
        installation, 12345, "generation", root, root
    )
    app = Path(environment_path(installation)) / "app"
    assert command[0] == str(app / "runtime/python.exe")
    assert str(app / "shiori_server.py") in command
    assert cwd == app
    config = json.loads(Path(command[-1]).read_text(encoding="utf-8"))["custom"]
    for field in (
        "t2s_weights_path",
        "vits_weights_path",
        "bert_base_path",
        "cnhuhbert_base_path",
    ):
        assert Path(config[field]).is_relative_to(app)
        assert not config[field].startswith("\\\\?\\")
    assert native_path(Path(environment["TEMP"])) == native_path(root) / "tmp"
    assert not environment["TEMP"].startswith("\\\\?\\")
