"""GlobalErrorCollector：零埋点地采集全局错误写入 observe.db。

接管四个全局错误出口（root logging handler / sys.excepthook /
asyncio loop exception handler / threading.excepthook），按 指纹 × 小时桶 在内存里
去重计数，后台 flush task 周期性 emit 给 TraceWriter 落库。安装/还原与插件生命周期绑定。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import traceback
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from shiori_sdk.diagnostics import (
    Diagnostics,
    SysExceptHook as _SysExceptHook,
    ThreadExceptHook as _ThreadExceptHook,
    LoopExceptHandler as _LoopExceptHandler,
)
from .events import GlobalErrorTrace

logger = logging.getLogger("observe.collector")

_FLUSH_INTERVAL = 10.0
_MESSAGE_MAX = 500
_TRACEBACK_MAX = 4000
_SESSION_KEYS_CAP = 20

# logging 采集跳过这些 logger（防自噬 + 避免 asyncio 双重计数：asyncio 任务异常走第 3 层）。
_SKIP_LOGGER_PREFIXES = ("observe", "plugin.observe", "asyncio")

# 指纹归一化：抹掉数字 / 十六进制 / 常见 id，使"同一个 bug"指纹稳定。
_NORM_HEX = re.compile(r"0x[0-9a-fA-F]+")
_NORM_NUM = re.compile(r"\d+")


def _empty_str_set() -> set[str]:
    return set()


class _Emitter(Protocol):
    def emit(self, event: GlobalErrorTrace) -> None: ...


@dataclass
class _BucketAgg:
    fingerprint: str
    bucket: str
    source: str
    logger_name: str
    error_type: str
    message: str
    traceback_text: str
    level: str
    first_ts: str
    last_ts: str
    count: int = 0
    session_keys: set[str] = field(default_factory=_empty_str_set)


class GlobalErrorCollector:
    def __init__(self, writer: _Emitter, diagnostics: Diagnostics) -> None:
        self._writer = writer
        self._diagnostics = diagnostics
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _BucketAgg] = {}
        self._flush_task: asyncio.Task[None] | None = None
        self._installed = False
        # 旧钩子，卸载时还原
        self._log_handler: logging.Handler | None = None
        self._prev_excepthook: _SysExceptHook | None = None
        self._prev_threadhook: _ThreadExceptHook | None = None
        self._prev_loop_handler: _LoopExceptHandler | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── 生命周期 ─────────────────────────────────

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        # 1. root logging handler（level >= ERROR）
        handler = _CollectorLogHandler(self)
        self._log_handler = handler
        # 4. asyncio 任务异常 + flush task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            self._loop = loop
            self._flush_task = loop.create_task(
                self._flush_loop(), name="observe_error_flush"
            )
        self._prev_excepthook, self._prev_threadhook, self._prev_loop_handler = (
            self._diagnostics.install_global_hooks(
                self,
                handler,
                self._on_sys_except,
                self._on_thread_except,
                loop,
                self._on_loop_except,
            )
        )
        logger.info("global error collector installed")

    async def uninstall(self) -> None:
        if not self._installed:
            return
        self._installed = False
        # 1. 还原钩子
        self._diagnostics.uninstall_global_hooks(self)
        self._log_handler = None
        # 2. 停 flush task 并最终 flush
        if self._flush_task is not None:
            _ = self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        self._flush()
        logger.info("global error collector uninstalled")

    # ── 采集入口 ─────────────────────────────────

    # 把一次错误折叠进内存的 (fingerprint, bucket) 桶。线程安全，绝不抛出。
    def capture(
        self,
        *,
        source: str,
        logger_name: str,
        error_type: str,
        message: str,
        traceback_text: str,
        level: str,
        top_frame: str,
        session_key: str | None,
    ) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            bucket = now[:13]
            fingerprint = _fingerprint(error_type, message, top_frame)
            key = (fingerprint, bucket)
            with self._lock:
                agg = self._buckets.get(key)
                if agg is None:
                    agg = _BucketAgg(
                        fingerprint=fingerprint,
                        bucket=bucket,
                        source=source,
                        logger_name=logger_name,
                        error_type=error_type,
                        message=message[:_MESSAGE_MAX],
                        traceback_text=traceback_text[:_TRACEBACK_MAX],
                        level=level,
                        first_ts=now,
                        last_ts=now,
                    )
                    self._buckets[key] = agg
                agg.count += 1
                agg.last_ts = now
                if session_key and len(agg.session_keys) < _SESSION_KEYS_CAP:
                    agg.session_keys.add(session_key)
        except Exception:
            # 采集器自身绝不影响主流程
            pass

    # ── 钩子回调 ─────────────────────────────────

    def _on_sys_except(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        tb: types.TracebackType | None,
    ) -> None:
        self._capture_exc("uncaught", "root", exc_type, exc_value, tb, "ERROR")
        if self._prev_excepthook is not None:
            _ = self._prev_excepthook(exc_type, exc_value, tb)

    def _on_thread_except(self, args: threading.ExceptHookArgs) -> None:
        thread_name = args.thread.name if args.thread is not None else "thread"
        self._capture_exc(
            "thread",
            thread_name,
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            "ERROR",
        )
        if self._prev_threadhook is not None:
            _ = self._prev_threadhook(args)

    def _on_loop_except(
        self, loop: asyncio.AbstractEventLoop, context: dict[str, object]
    ) -> None:
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            self._capture_exc(
                "asyncio", "asyncio", type(exc), exc, exc.__traceback__, "ERROR"
            )
        else:
            msg = str(context.get("message", "asyncio error"))
            self.capture(
                source="asyncio",
                logger_name="asyncio",
                error_type="AsyncioError",
                message=msg,
                traceback_text=msg,
                level="ERROR",
                top_frame="asyncio",
                session_key=None,
            )
        if self._prev_loop_handler is not None:
            _ = self._prev_loop_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    def _capture_exc(
        self,
        source: str,
        logger_name: str,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: types.TracebackType | None,
        level: str,
    ) -> None:
        type_name = exc_type.__name__ if exc_type else "Error"
        message = str(exc_value) if exc_value else type_name
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        self.capture(
            source=source,
            logger_name=logger_name,
            error_type=type_name,
            message=message,
            traceback_text=tb_text,
            level=level,
            top_frame=self._diagnostics.top_frame(tb),
            session_key=self._diagnostics.session_key(),
        )

    # ── flush ────────────────────────────────────

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            self._flush()

    # 把内存里累计的增量 emit 给 writer（writer 端 UPSERT 累加），随后清空。
    def _flush(self) -> None:
        with self._lock:
            if not self._buckets:
                return
            pending = list(self._buckets.values())
            self._buckets.clear()
        for agg in pending:
            self._writer.emit(
                GlobalErrorTrace(
                    fingerprint=agg.fingerprint,
                    bucket=agg.bucket,
                    source=agg.source,
                    logger_name=agg.logger_name,
                    error_type=agg.error_type,
                    message=agg.message,
                    traceback_text=agg.traceback_text,
                    level=agg.level,
                    first_ts=agg.first_ts,
                    last_ts=agg.last_ts,
                    count=agg.count,
                    session_keys=list(agg.session_keys),
                )
            )


class _CollectorLogHandler(logging.Handler):
    def __init__(self, collector: GlobalErrorCollector) -> None:
        super().__init__(level=logging.ERROR)
        self._collector = collector

    def emit(self, record: logging.LogRecord) -> None:
        try:
            name = record.name or ""
            if any(name.startswith(p) for p in _SKIP_LOGGER_PREFIXES):
                return
            exc_info = record.exc_info
            if exc_info and exc_info[0] is not None:
                exc_type, exc_value, tb = exc_info
                error_type = exc_type.__name__
                message = str(exc_value) if exc_value else record.getMessage()
                tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
                top_frame = self._collector._diagnostics.top_frame(tb)
            else:
                error_type = "LogError"
                message = record.getMessage()
                tb_text = f"{name}: {message}\n  at {record.pathname}:{record.lineno}"
                top_frame = f"{record.pathname}:{record.lineno}"
            self._collector.capture(
                source="log",
                logger_name=name,
                error_type=error_type,
                message=message,
                traceback_text=tb_text,
                level=record.levelname,
                top_frame=top_frame,
                session_key=self._collector._diagnostics.session_key(),
            )
        except Exception:
            pass


# ── 辅助 ─────────────────────────────────────────


def _fingerprint(error_type: str, message: str, top_frame: str) -> str:
    norm = _NORM_NUM.sub("#", _NORM_HEX.sub("#", message))
    raw = f"{error_type}|{norm}|{top_frame}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
