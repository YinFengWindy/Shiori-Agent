"""
入口

正式模式：
  python main.py          启动桌面 bridge 主链
  python main.py bridge   启动桌面 bridge 主链
"""

from __future__ import annotations

import argparse
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


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 Mira-Agent runtime")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("bridge", "desktop", "setup", "init"),
        help="运行命令；desktop 是 bridge 的兼容别名",
    )
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--workspace", type=Path, help="工作区路径")
    parser.add_argument("--force", action="store_true", help="初始化时覆盖现有文件")
    parser.add_argument(
        "--inspect-modules",
        action="store_true",
        help="输出模块检查结果后退出",
    )
    return parser


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
        print(await runtime.inspect_modules())
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


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并执行对应的 runtime 入口。"""
    configure_logging_stream(sys.stderr)
    args = _build_argument_parser().parse_args(argv)
    config_path = str(args.config)
    workspace = args.workspace

    if args.command == "setup":
        from bootstrap.setup_wizard import run_setup_wizard

        run_setup_wizard(
            config_path=Path(config_path),
            workspace=workspace or resolve_default_workspace(),
        )
        return 0

    if args.command == "init":
        summary = init_workspace(
            config_path=config_path,
            workspace=workspace or resolve_default_workspace(),
            force=args.force,
        )
        _log_init_summary(summary)
        return 0

    if not Path(config_path).exists():
        logger.error(
            f"找不到配置文件 {config_path!r}，请先复制 config.example.toml 为 config.toml。"
        )
        return 1

    if args.inspect_modules:
        asyncio.run(inspect_modules(config_path, workspace))
    else:
        asyncio.run(serve_bridge(config_path, workspace))
    return 0


if __name__ == "__main__":
    sys.exit(main())
