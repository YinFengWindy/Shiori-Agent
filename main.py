"""
入口

正式模式：
  python main.py          启动桌面 bridge 主链
  python main.py bridge   启动桌面 bridge 主链
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from agent.config import Config
from bootstrap.app import (
    DESKTOP_RUNTIME_FEATURES,
    build_app_runtime,
    configure_logging_stream,
)
from bootstrap.init_workspace import InitSummary, init_workspace
from core.common.workspace import resolve_default_workspace
from core.net.http import SharedHttpResources
from desktop_bridge import DesktopBridgeServer

logger = logging.getLogger(__name__)


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
        workspace or resolve_default_workspace(),
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
    runtime = build_app_runtime(
        Config.load(config_path),
        workspace=workspace or resolve_default_workspace(),
        features=DESKTOP_RUNTIME_FEATURES,
    )
    try:
        await runtime.start()
        core_runtime = runtime.core
        if core_runtime is None:
            raise RuntimeError("desktop bridge runtime 未正确初始化 core")
        server = DesktopBridgeServer(core_runtime)
        await server.serve_stdio()
    finally:
        await runtime.shutdown()


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
            workspace=workspace or resolve_default_workspace(),
        )
        sys.exit(0)

    if args and args[0] == "init":
        summary = init_workspace(
            config_path=config_path,
            workspace=workspace or resolve_default_workspace(),
            force=force,
        )
        _log_init_summary(summary)
        sys.exit(0)

    if args and args[0] == "bridge":
        asyncio.run(serve_bridge(config_path, workspace))
        sys.exit(0)

    if args and not args[0].startswith("-"):
        logger.error("未知命令: %s", args[0])
        sys.exit(2)

    if not Path(config_path).exists():
        logger.error(
            f"找不到配置文件 {config_path!r}，请先复制 config.example.toml 为 config.toml。"
        )
        sys.exit(1)

    if "--inspect-modules" in args:
        asyncio.run(inspect_modules(config_path, workspace))
    else:
        asyncio.run(serve_bridge(config_path, workspace))
