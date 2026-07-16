"""Repository registry hydration for Coding Agent orchestration."""

from __future__ import annotations

from typing import Any

from .models import CodingRepository
from .repository_trust import RepositoryTrustService, TrustedRepository
from .store import CodingAgentStore


def load_repository_state(
    config: Any,
    store: CodingAgentStore,
    trust_service: RepositoryTrustService,
) -> tuple[dict[str, TrustedRepository], dict[str, str]]:
    """Load configured and recoverable persisted repositories."""

    repositories: dict[str, TrustedRepository] = {}
    base_refs: dict[str, str] = {}
    for project_id, project in config.coding_agents.projects.items():
        resolution = trust_service.resolve(project.repo_path)
        repository = TrustedRepository(
            repository_id=project_id,
            name=project_id,
            root_path=resolution.repository.root_path,
            head_commit=resolution.repository.head_commit,
        )
        trust_service.register(repository)
        repositories[project_id] = repository
        base_refs[project_id] = project.base_ref
        if store.get_repository(project_id) is None:
            store.create_repository(
                CodingRepository(
                    id=project_id,
                    name=project_id,
                    root_path=str(repository.root_path),
                    trusted=True,
                )
            )

    active_repository_ids = {
        task.repository_id
        for task in store.list_tasks()
        if task.status.value not in {"succeeded", "failed", "cancelled"}
    }
    for record in store.list_repositories():
        if not record.trusted and record.id not in active_repository_ids:
            continue
        resolution = trust_service.resolve(record.root_path)
        repository = TrustedRepository(
            repository_id=record.id,
            name=record.name,
            root_path=resolution.repository.root_path,
            head_commit=resolution.repository.head_commit,
        )
        trust_service.register(repository)
        repositories[record.id] = repository
    return repositories, base_refs
