from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import main as app_main


@pytest.mark.parametrize("initial_encoding", ["utf-8", "cp936"])
def test_bridge_keeps_dependency_prints_off_protocol_pipe(
    tmp_path: Path, initial_encoding: str
):
    """Exercise the real stdio writer with noisy runtime stages and a worker thread."""
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    probe = dedent("""
        import asyncio
        import json
        import sys
        from types import SimpleNamespace
        import main
        from desktop_bridge.config_transaction import ConfigTransaction
        from desktop_bridge.server import DesktopBridgeServer

        sys.stdin.reconfigure(encoding=sys.argv[2])
        sys.stdout.reconfigure(encoding=sys.argv[2])
        sys.stderr.reconfigure(encoding=sys.argv[2])
        protocol_output = sys.stdout

        def recover(self):
            print("recovery: 配置恢复")

        def load(*args, **kwargs):
            print("config: 配置加载")
            return object()

        async def start():
            print({("ncatbot_status",): None}.keys(), {("ncs",): None}.keys())
            await asyncio.to_thread(print, "thread: 后台线程")

        async def shutdown():
            await asyncio.to_thread(print, "shutdown: 关闭通道")

        def build(*args, **kwargs):
            print("construction: 创建运行时")
            return SimpleNamespace(core=object(), start=start, shutdown=shutdown)

        class Server(DesktopBridgeServer):
            def __init__(self, *args, **kwargs):
                print("server: 创建服务")

            async def serve_streams(self, *, read_line, write_payload):
                request = json.loads(await read_line())
                await asyncio.to_thread(print, "runtime: 请求处理")
                await write_payload({
                    "id": request["id"], "type": "response",
                    "method": request["method"], "payload": {"name": "栞"},
                })
                await write_payload({
                    "id": "event-1", "type": "event",
                    "method": "chat.event", "payload": {"text": "你好"},
                })

        ConfigTransaction.recover = recover
        main.Config.load = load
        main.build_app_runtime = build
        main.DesktopBridgeServer = Server
        assert main.main(["bridge", "--config", sys.argv[1]]) == 0
        assert sys.stdout is protocol_output
        """)
    result = subprocess.run(
        [sys.executable, "-c", probe, str(config_path), initial_encoding],
        cwd=Path(app_main.__file__).parent,
        input=(
            json.dumps({"id": "settings-1", "method": "settings.read"}) + "\n"
        ).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )

    stderr = result.stderr.decode("utf-8")
    assert result.returncode == 0, stderr
    frames = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    assert frames == [
        {
            "id": "settings-1",
            "type": "response",
            "method": "settings.read",
            "payload": {"name": "栞"},
        },
        {
            "id": "event-1",
            "type": "event",
            "method": "chat.event",
            "payload": {"text": "你好"},
        },
    ]
    for diagnostic in (
        "recovery: 配置恢复",
        "config: 配置加载",
        "construction: 创建运行时",
        "dict_keys([('ncatbot_status',)]) dict_keys([('ncs',)])",
        "thread: 后台线程",
        "server: 创建服务",
        "runtime: 请求处理",
        "shutdown: 关闭通道",
    ):
        assert diagnostic in stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_stage", ["recovery", "config", "build", "start", "serve", "shutdown"]
)
async def test_bridge_restores_stdout_and_propagates_failures(
    failure_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    original_stdout = sys.stdout
    stages: list[str] = []

    def enter(stage):
        stages.append(stage)
        print(stage)
        if stage == failure_stage:
            raise RuntimeError(f"failed {stage}")

    async def start():
        enter("start")

    async def shutdown():
        enter("shutdown")

    async def serve_stdio(**kwargs):
        enter("serve")

    def build(*args, **kwargs):
        enter("build")
        return SimpleNamespace(core=object(), start=start, shutdown=shutdown)

    monkeypatch.setattr(
        "desktop_bridge.config_transaction.ConfigTransaction.recover",
        lambda self: enter("recovery"),
    )
    monkeypatch.setattr(
        app_main.Config, "load", lambda *args, **kwargs: enter("config")
    )
    monkeypatch.setattr(app_main, "build_app_runtime", build)
    monkeypatch.setattr(
        app_main,
        "DesktopBridgeServer",
        lambda *args, **kwargs: SimpleNamespace(serve_stdio=serve_stdio),
    )

    with pytest.raises(RuntimeError, match=f"failed {failure_stage}"):
        await app_main.serve_bridge(workspace=tmp_path)

    assert sys.stdout is original_stdout
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == stages
    if failure_stage in {"start", "serve", "shutdown"}:
        assert stages[-1] == "shutdown"


def test_main_help_prints_usage(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        app_main.main(["--help"])

    assert exc_info.value.code == 0
    assert "bridge" in capsys.readouterr().out


def test_main_accepts_desktop_as_bridge_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    serve_bridge = AsyncMock()
    monkeypatch.setattr(app_main, "serve_bridge", serve_bridge)

    exit_code = app_main.main(["desktop", "--config", str(config_path)])

    assert exit_code == 0
    serve_bridge.assert_awaited_once_with(str(config_path), None)


@pytest.mark.asyncio
async def test_inspect_modules_prints_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    class _Runtime:
        memory_runtime = SimpleNamespace(aclose=AsyncMock())

        async def inspect_modules(self):
            return {"memory": "ready"}

        async def stop(self):
            return None

    class _HttpResources:
        async def aclose(self):
            return None

    loader = Mock(return_value=object())
    monkeypatch.setattr(app_main.Config, "load", loader)
    monkeypatch.setattr(app_main, "SharedHttpResources", _HttpResources)
    monkeypatch.setattr(
        "bootstrap.tools.build_core_runtime",
        lambda config, workspace, http_resources: _Runtime(),
    )

    await app_main.inspect_modules(workspace=tmp_path)

    loader.assert_called_once_with("config.toml", workspace=tmp_path)
    assert "{'memory': 'ready'}" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_bridge_loads_plugin_settings_using_explicit_workspace(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    package = tmp_path / "packages/demo"
    package.mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    legacy = workspace / "plugins/demo/plugin_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"value":"kept"}', encoding="utf-8")
    path = tmp_path / "elsewhere/config.toml"
    path.parent.mkdir()
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "agent.plugin_config_migration.plugin_roots", lambda: [package.parent]
    )
    monkeypatch.setattr("agent.plugin_config_migration.REPOSITORY_ROOT", tmp_path)
    runtime = SimpleNamespace(start=AsyncMock(), shutdown=AsyncMock(), core=object())
    builder = Mock(return_value=runtime)
    monkeypatch.setattr(app_main, "build_app_runtime", builder)
    monkeypatch.setattr(
        app_main,
        "DesktopBridgeServer",
        lambda *args, **kwargs: SimpleNamespace(serve_stdio=AsyncMock()),
    )
    await app_main.serve_bridge(str(path), workspace)
    assert builder.call_args.args[0].plugins["demo"] == {"value": "kept"}
    assert builder.call_args.kwargs["workspace"] == workspace
    runtime.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_inspection_closes_http_when_construction_fails(
    monkeypatch, tmp_path
):
    http = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(app_main.Config, "load", lambda _, **kwargs: object())
    monkeypatch.setattr(app_main, "SharedHttpResources", lambda: http)

    def fail(*args):
        raise ValueError("invalid wiring")

    monkeypatch.setattr("bootstrap.tools.build_core_runtime", fail)
    with pytest.raises(ValueError, match="invalid wiring"):
        await app_main.inspect_modules(workspace=tmp_path)
    http.aclose.assert_awaited_once()


def test_dev_launch_makes_top_level_plugins_importable(tmp_path: Path):
    """开发态启动形态下，入口必须让 `plugins.<id>` 可导入。

    桌面 dev 用 `python main.py` 以 apps/backend 为脚本目录启动后端，仓库根不在
    sys.path 上；而插件包内部与 bootstrap 的默认记忆引擎都用 plugins.<id>.<module>
    绝对导入。少了入口这一步，插件会在导入期全部失败并被内核静默跳过。

    pytest 自身的 `pythonpath = . apps/backend` 恰好会掩盖这个缺口，所以这里用
    子进程复刻真实的 sys.path 形态，而不是在当前进程里断言。
    """
    import subprocess
    import sys

    repository_root = Path(__file__).resolve().parents[2]
    backend_root = repository_root / "apps" / "backend"
    workspace = tmp_path / "workspace"
    config_path = tmp_path / "config.toml"

    probe = "\n".join(
        [
            "import sys",
            f"sys.path[:] = [p for p in sys.path if p != {str(repository_root)!r}]",
            "import main",
            f"code = main.main(['init', '--workspace', {str(workspace)!r},"
            f" '--config', {str(config_path)!r}])",
            "import plugins.default_memory.backend.config",
            "print('PLUGINS_IMPORTABLE', code)",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_root,
        capture_output=True,
        # 入口把 stdout/stderr 统一成 UTF-8，而 text=True 按宿主 locale 解码
        # （中文 Windows 上是 cp936），读取线程会以 UnicodeDecodeError 死掉，
        # 测试于是只在 UTF-8 locale 的 CI 上通过。显式固定编码。
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
    assert "PLUGINS_IMPORTABLE 0" in result.stdout


@pytest.mark.asyncio
async def test_module_entrypoint_exit_codes(monkeypatch: pytest.MonkeyPatch):
    """以 `python -m main` 方式运行时的三条退出路径。"""
    import runpy
    import sys

    monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "missing.json"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("main", run_name="__main__")
    assert exc.value.code == 1

    def _fake_asyncio_run(coro):
        coro.close()
        return None

    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
    monkeypatch.setattr("asyncio.run", _fake_asyncio_run)
    monkeypatch.setattr(
        "agent.config.Config.load",
        classmethod(lambda cls, path="config.toml", **kwargs: SimpleNamespace()),
    )
    monkeypatch.setattr(
        "bootstrap.app.build_app_runtime",
        lambda *args, **kwargs: SimpleNamespace(run=AsyncMock()),
    )
    monkeypatch.setattr(sys, "argv", ["main.py", "cli"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("main", run_name="__main__")
    assert exc.value.code == 2

    monkeypatch.setattr(sys, "argv", ["main.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("main", run_name="__main__")
    assert exc.value.code == 0
