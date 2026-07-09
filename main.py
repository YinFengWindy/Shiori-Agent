"""
入口

正式模式：
  python main.py          启动桌面 bridge 主链
  python main.py bridge   启动桌面 bridge 主链
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import suppress
from pathlib import Path

from agent.config import Config
from bootstrap.app import (
    DESKTOP_RUNTIME_FEATURES,
    SERVICE_RUNTIME_FEATURES,
    RuntimeFeatures,
    build_app_runtime,
    configure_logging_stream,
)
from bootstrap.init_workspace import InitSummary, init_workspace
from bootstrap.tools import build_core_runtime
from core.net.http import SharedHttpResources
from desktop_bridge import DesktopBridgeServer

logger = logging.getLogger(__name__)
_REMOVED_ENTRYPOINT_MESSAGES = {
    "cli": "`python main.py cli` 已从正式后端入口移除。",
    "desktop": "`python main.py desktop` 已从正式后端入口移除。",
    "dashboard": "`python main.py dashboard` 已从正式后端入口移除。",
    "gateway": "`python main.py gateway` 已从正式后端入口移除。",
}


def _default_workspace() -> Path:
    return Path.home() / ".akashic" / "workspace"


def _get_flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        raise ValueError(f"参数 {flag} 缺少值")
    return args[idx + 1]


def _log_init_summary(summary: InitSummary) -> None:
    def _log_group(title: str, paths: list[Path]) -> None:
        if not paths:
            return
        logger.info("%s", title)
        for path in paths:
            logger.info("  %s", path)

    _log_group("已创建：", summary.created)
    _log_group("已覆盖：", summary.overwritten)
    _log_group("已跳过：", summary.skipped)
    if summary.notes:
        logger.info("说明：")
        for note in summary.notes:
            logger.info("  %s", note)
    if summary.next_steps:
        logger.info("下一步：")
        for step in summary.next_steps:
            logger.info("  %s", step)


def _exit_removed_entrypoint(name: str) -> None:
    message = _REMOVED_ENTRYPOINT_MESSAGES.get(name, f"`python main.py {name}` 已移除。")
    logger.error("%s 请改用 `python main.py bridge` 或桌面端启动脚本。", message)
    sys.exit(2)


async def inspect_modules(
    config_path: str = "config.toml",
    workspace: Path | None = None,
) -> None:
    import logging
    from bootstrap.tools import build_core_runtime

    logging.getLogger().setLevel(logging.WARNING)
    config = Config.load(config_path)
    http_resources = SharedHttpResources()
    runtime = build_core_runtime(
        config,
        workspace or _default_workspace(),
        http_resources,
    )
    try:
        logger.info("%s", await runtime.inspect_modules())
    finally:
        await runtime.stop()
        await http_resources.aclose()


async def serve_bridge(
    config_path: str = "config.toml",
    workspace: Path | None = None,
) -> None:
    configure_logging_stream(sys.stderr)
    fallback_core_runtime = None
    fallback_http_resources = None
    runtime = build_app_runtime(
        Config.load(config_path),
        workspace=workspace or _default_workspace(),
        features=DESKTOP_RUNTIME_FEATURES,
    )
    try:
        if hasattr(runtime, "start") and callable(runtime.start):
            await runtime.start()
            core_runtime = getattr(runtime, "core", None)
        else:
            fallback_http_resources = SharedHttpResources()
            fallback_core_runtime = build_core_runtime(
                Config.load(config_path),
                workspace or _default_workspace(),
                fallback_http_resources,
            )
            core_runtime = fallback_core_runtime
            await core_runtime.start()
        if core_runtime is None:
            raise RuntimeError("desktop bridge runtime 未正确初始化 core")
        server = DesktopBridgeServer(core_runtime)
        await server.serve_stdio()
    finally:
        if hasattr(runtime, "shutdown") and callable(runtime.shutdown):
            await runtime.shutdown()
        if fallback_core_runtime is not None:
            await fallback_core_runtime.stop()
        if fallback_http_resources is not None:
            await fallback_http_resources.aclose()


async def serve(
    config_path: str = "config.toml",
    workspace: Path | None = None,
    *,
    features: RuntimeFeatures = SERVICE_RUNTIME_FEATURES,
) -> None:
    config = Config.load(config_path)
    runtime = build_app_runtime(
        config,
        workspace=workspace or _default_workspace(),
        features=features,
    )
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    watched_signals = (signal.SIGINT, signal.SIGTERM)
    signal_handlers_registered = False
    for sig in watched_signals:
        try:
            loop.add_signal_handler(sig, stop_event.set)
            signal_handlers_registered = True
        except NotImplementedError:
            # Windows' default event loop does not support add_signal_handler.
            signal.signal(
                sig,
                lambda _sig, _frame: loop.call_soon_threadsafe(stop_event.set),
            )

    runtime_task = asyncio.create_task(runtime.run(), name="app_runtime")
    stop_task = asyncio.create_task(stop_event.wait(), name="shutdown_signal")
    try:
        done, _ = await asyncio.wait(
            {runtime_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if runtime_task in done:
            _ = stop_task.cancel()
            await runtime_task
            return
        _ = runtime_task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime_task
    finally:
        if signal_handlers_registered:
            for sig in watched_signals:
                _ = loop.remove_signal_handler(sig)
        _ = stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task


if __name__ == "__main__":
    configure_logging_stream(sys.stderr)
    args = sys.argv[1:]
    config_path = "config.toml"
    workspace: Path | None = None
    force = "--force" in args

    try:
        config_value = _get_flag_value(args, "--config")
        workspace_value = _get_flag_value(args, "--workspace")
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if config_value is not None:
        config_path = config_value
    if workspace_value is not None:
        workspace = Path(workspace_value)

    if args and args[0] == "setup":
        from bootstrap.setup_wizard import run_setup_wizard
        run_setup_wizard(
            config_path=Path(config_path),
            workspace=workspace or _default_workspace(),
        )
        sys.exit(0)

    if args and args[0] == "init":
        summary = init_workspace(
            config_path=config_path,
            workspace=workspace or _default_workspace(),
            force=force,
        )
        _log_init_summary(summary)
        sys.exit(0)

    if args and args[0] in {"gateway", "desktop", "cli", "dashboard"}:
        _exit_removed_entrypoint(args[0])

    if args and args[0] == "bridge":
        asyncio.run(serve_bridge(config_path, workspace))
        sys.exit(0)

    if not Path(config_path).exists():
        logger.error(
            f"找不到配置文件 {config_path!r}，请先复制 config.example.toml 为 config.toml。"
        )
        sys.exit(1)

    if "--inspect-modules" in args:
        asyncio.run(inspect_modules(config_path, workspace))
    else:
        asyncio.run(serve_bridge(config_path, workspace))
