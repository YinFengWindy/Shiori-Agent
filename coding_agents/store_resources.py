"""Repository trust records and worktree mappings for CodingAgentStore."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import AbstractContextManager

from .models import CodingRepository, CodingTaskRun, CodingWorkspace, WorkspaceStatus, utc_now
from .store_approvals import CodingAgentRecordNotFound
from .store_rows import row_to_repository, row_to_workspace


class StoreResourcesMixin:
    """Persist configured repositories and their allocated workspaces."""

    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _transaction(self) -> AbstractContextManager[None]:
        raise NotImplementedError

    def _get_run_locked(self, run_id: str) -> CodingTaskRun | None:
        raise NotImplementedError

    def create_repository(self, repository: CodingRepository) -> CodingRepository:
        """Persist a configured repository and its current trust decision."""

        if not repository.name.strip() or not repository.root_path.strip():
            raise ValueError("repository name and root_path must not be empty")
        with self._transaction():
            self._connection.execute(
                """INSERT INTO coding_repositories
                   (id, name, root_path, trusted, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    repository.id,
                    repository.name,
                    repository.root_path,
                    int(repository.trusted),
                    repository.created_at,
                    repository.updated_at,
                ),
            )
            return repository

    def get_repository(self, repository_id: str) -> CodingRepository | None:
        """Return a configured repository by ID."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_repositories WHERE id = ?", (repository_id,)
            ).fetchone()
            return row_to_repository(row) if row else None

    def get_repository_by_root_path(self, root_path: str) -> CodingRepository | None:
        """Return a configured repository by its unique root path."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_repositories WHERE root_path = ?", (root_path,)
            ).fetchone()
            return row_to_repository(row) if row else None

    def list_repositories(self, *, trusted: bool | None = None) -> list[CodingRepository]:
        """List configured repositories, optionally filtered by trust."""

        query = "SELECT * FROM coding_repositories"
        values: tuple[int, ...] = ()
        if trusted is not None:
            query += " WHERE trusted = ?"
            values = (int(trusted),)
        query += " ORDER BY created_at, id"
        with self._lock:
            rows = self._connection.execute(query, values).fetchall()
            return [row_to_repository(row) for row in rows]

    def update_repository_trust(
        self, repository_id: str, *, trusted: bool
    ) -> CodingRepository:
        """Durably replace a repository trust decision."""

        with self._transaction():
            if self.get_repository(repository_id) is None:
                raise CodingAgentRecordNotFound(
                    f"repository not found: {repository_id}"
                )
            self._connection.execute(
                "UPDATE coding_repositories SET trusted = ?, updated_at = ? WHERE id = ?",
                (int(trusted), utc_now(), repository_id),
            )
            repository = self.get_repository(repository_id)
            assert repository is not None
            return repository

    set_repository_trusted = update_repository_trust

    def update_repository(self, repository: CodingRepository) -> CodingRepository:
        """Replace the mutable configuration and trust fields of a repository."""

        if not repository.name.strip() or not repository.root_path.strip():
            raise ValueError("repository name and root_path must not be empty")
        with self._transaction():
            current = self.get_repository(repository.id)
            if current is None:
                raise CodingAgentRecordNotFound(
                    f"repository not found: {repository.id}"
                )
            updated_at = utc_now()
            self._connection.execute(
                """UPDATE coding_repositories
                   SET name = ?, root_path = ?, trusted = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    repository.name,
                    repository.root_path,
                    int(repository.trusted),
                    updated_at,
                    repository.id,
                ),
            )
            updated = self.get_repository(repository.id)
            assert updated is not None
            return updated

    def create_workspace(self, workspace: CodingWorkspace) -> CodingWorkspace:
        """Persist a run/worktree mapping and mirror it onto the run snapshot."""

        if not workspace.worktree_path.strip():
            raise ValueError("workspace worktree_path must not be empty")
        with self._transaction():
            if self._get_run_locked(workspace.run_id) is None:
                raise CodingAgentRecordNotFound(f"run not found: {workspace.run_id}")
            repository = self._connection.execute(
                "SELECT id FROM coding_repositories WHERE id = ?",
                (workspace.repository_id,),
            ).fetchone()
            if repository is None:
                raise CodingAgentRecordNotFound(
                    f"repository not found: {workspace.repository_id}"
                )
            self._connection.execute(
                """INSERT INTO coding_workspaces
                   (id, run_id, repository_id, worktree_path, baseline_commit,
                    branch_name, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    workspace.id,
                    workspace.run_id,
                    workspace.repository_id,
                    workspace.worktree_path,
                    workspace.baseline_commit,
                    workspace.branch_name,
                    workspace.status,
                    workspace.created_at,
                    workspace.updated_at,
                ),
            )
            self._connection.execute(
                """UPDATE coding_task_runs
                   SET workspace_id = ?, worktree_path = ?, baseline_commit = ?,
                       branch_name = ? WHERE id = ?""",
                (
                    workspace.id,
                    workspace.worktree_path,
                    workspace.baseline_commit,
                    workspace.branch_name,
                    workspace.run_id,
                ),
            )
            return workspace

    def get_workspace(self, workspace_id: str) -> CodingWorkspace | None:
        """Return a persisted workspace by ID."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()
            return row_to_workspace(row) if row else None

    def get_workspace_by_run(self, run_id: str) -> CodingWorkspace | None:
        """Return the unique workspace allocated to a run."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_workspaces WHERE run_id = ?", (run_id,)
            ).fetchone()
            return row_to_workspace(row) if row else None

    def list_workspaces(
        self,
        *,
        repository_id: str | None = None,
        status: WorkspaceStatus | str | None = None,
    ) -> list[CodingWorkspace]:
        """List workspace mappings with optional repository and state filters."""

        clauses: list[str] = []
        values: list[str] = []
        if repository_id is not None:
            clauses.append("repository_id = ?")
            values.append(repository_id)
        if status is not None:
            clauses.append("status = ?")
            values.append(WorkspaceStatus(status))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM coding_workspaces{where} ORDER BY created_at, id",
                values,
            ).fetchall()
            return [row_to_workspace(row) for row in rows]

    def update_workspace_status(
        self, workspace_id: str, status: WorkspaceStatus | str
    ) -> CodingWorkspace:
        """Update durable workspace lifecycle state without changing its mapping."""

        next_status = WorkspaceStatus(status)
        with self._transaction():
            current = self.get_workspace(workspace_id)
            if current is None:
                raise CodingAgentRecordNotFound(f"workspace not found: {workspace_id}")
            self._connection.execute(
                "UPDATE coding_workspaces SET status = ?, updated_at = ? WHERE id = ?",
                (next_status, utc_now(), workspace_id),
            )
            updated = self.get_workspace(workspace_id)
            assert updated is not None
            return updated

    create_coding_repository = create_repository
    get_coding_repository = get_repository
    list_coding_repositories = list_repositories
    update_coding_repository = update_repository
    create_coding_workspace = create_workspace
    get_coding_workspace = get_workspace
    list_coding_workspaces = list_workspaces
    update_coding_workspace_status = update_workspace_status
