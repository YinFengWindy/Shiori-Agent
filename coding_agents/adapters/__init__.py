"""Coding Agent CLI 适配器公共入口。"""

from .base import (
    AdapterError,
    AdapterEvent,
    AdapterResult,
    CodingAgentAdapter,
    PreparedRun,
    ProbeResult,
    ResumeSpec,
    RunHandle,
    TaskRunSpec,
)
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .process import (
    AsyncioProcessRunner,
    CapturedProcess,
    ManagedProcess,
    ProcessRunner,
)

__all__ = [
    "AdapterError",
    "AdapterEvent",
    "AdapterResult",
    "AsyncioProcessRunner",
    "CapturedProcess",
    "ClaudeAdapter",
    "CodexAdapter",
    "CodingAgentAdapter",
    "ManagedProcess",
    "PreparedRun",
    "ProbeResult",
    "ProcessRunner",
    "ResumeSpec",
    "RunHandle",
    "TaskRunSpec",
]
