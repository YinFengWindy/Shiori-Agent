"""Small immutable DTO and serialization helpers for orchestration."""

from __future__ import annotations

import os
from typing import Any

from .models import CodingTask, CodingTaskRun


def profile_mapping(profiles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Adapt validated app config profiles to the strict domain registry."""

    return {
        profile_id: {
            "provider": profile.provider,
            "model": profile.model,
            "effort": profile.effort,
            "timeout_seconds": profile.timeout_seconds,
            "max_parallel_runs": profile.max_parallel_runs,
            "max_permission_level": profile.max_permission_level,
            "max_budget_usd": profile.max_budget_usd,
        }
        for profile_id, profile in profiles.items()
    }


def project_parallel_limit(config: Any, repository_id: str) -> int:
    """Return a registered project's concurrency limit or the dynamic default."""

    project = config.coding_agents.projects.get(repository_id)
    return project.max_parallel_runs if project is not None else 1


def safe_environment() -> dict[str, str]:
    """Build a small CLI environment instead of forwarding all Shiori secrets."""

    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "CODEX_HOME",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def task_json(task: CodingTask) -> dict[str, Any]:
    """Serialize the role-visible task fields."""

    return {
        "id": task.id,
        "title": task.title,
        "mode": task.mode.value,
        "status": task.status.value,
        "repository_id": task.repository_id,
        "request_text": task.request_text,
    }


def run_json(run: CodingTaskRun) -> dict[str, Any]:
    """Serialize the role-visible run fields."""

    return {
        "id": run.id,
        "status": run.status.value,
        "provider": run.provider.value,
        "profile_id": run.profile_id,
        "permission_level": run.permission_level.value,
        "worktree_path": run.worktree_path,
        "result_summary": run.result_summary,
        "error_code": run.error_code,
    }
