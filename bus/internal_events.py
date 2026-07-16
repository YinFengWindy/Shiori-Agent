from __future__ import annotations

from dataclasses import dataclass

SPAWN_COMPLETED = "spawn_completed"
CODING_AGENT_COMPLETED = "coding_agent_completed"


@dataclass(frozen=True)
class SpawnCompletionEvent:
    job_id: str
    label: str
    task: str
    status: str
    exit_reason: str
    result: str
    retry_count: int = 0
    profile: str = ""


@dataclass(frozen=True)
class CodingAgentCompletionEvent:
    """Persisted Coding Agent run result routed back to its manager role."""

    task_id: str
    run_id: str
    label: str
    task: str
    mode: str
    status: str
    provider: str
    profile_id: str
    result: str
    thread_id: str
    manager_role_id: str
    request_id: str
    delivery_key: str
    error_code: str = ""
    artifacts: tuple[str, ...] = ()
