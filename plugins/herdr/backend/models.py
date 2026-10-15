"""One running Shiori process owns these task snapshots; no restart recovery."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from shiori_sdk.background_results import BackgroundResultTarget

from .config import AgentKind, HerdrConfig

type TaskStatus = Literal[
    "queued",
    "preparing",
    "running",
    "completed",
    "blocked",
    "unknown",
    "failed",
    "cancelling",
    "cancelled",
    "monitoring_stopped",
]


def now() -> str:
    """UTC timestamp for task snapshots and later dashboard consumers."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CodingTask:
    """Owned task identity, Herdr lifecycle, and independently checked delivery."""

    id: str
    requirement: str
    repository: Path
    agent: AgentKind
    target: BackgroundResultTarget
    directory: Path
    branch: str
    run_id: str
    config: HerdrConfig = field(default_factory=HerdrConfig)
    status: TaskStatus = "queued"
    agent_state: str = "unknown"
    prompt_settled: bool = False
    prompt_sent: bool = False
    revision: int = 0
    stage: str = ""
    progress_sequence: int = 0
    progress_notice: str = ""
    progress_events: list[dict[str, object]] = field(default_factory=list)
    worktree: Path | None = None
    workspace_id: str = ""
    pane_id: str = ""
    agent_name: str = ""
    base_commit: str = ""
    summary: str = ""
    validation: list[dict[str, object]] = field(default_factory=list)
    pr_url: str = ""
    output: str = ""
    error: str = ""
    report_error: str = ""
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    worker: asyncio.Task[None] | None = field(default=None, repr=False)
    operation_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def touch(self, status: TaskStatus | None = None) -> None:
        """Update observation time without conflating lifecycle with delivery."""
        if status is not None:
            self.status = status
        self.updated_at = now()
        self.revision += 1

    @property
    def result_path(self) -> Path:
        """Separate artifact for each task attempt; never reuse a previous result."""
        return self.directory / f"{self.run_id}.json"

    @property
    def progress_path(self) -> Path:
        """Each run owns a separate structured progress log."""
        return self.directory / f"{self.run_id}.progress.jsonl"
