"""Explicit approval persistence operations for CodingAgentStore."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    CodingTaskRun,
    RunStatus,
    utc_now,
)
from .state_machine import TERMINAL_RUN_STATUSES, require_run_transition
from .store_rows import dump_json, row_to_approval


class CodingAgentRecordNotFound(LookupError):
    """Raised when a requested Coding Agent store record does not exist."""


class StoreApprovalsMixin:
    """Persist approval gates and their atomic Run transitions."""

    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _transaction(self) -> AbstractContextManager[None]:
        raise NotImplementedError

    def _append_event_locked(
        self,
        *,
        task_id: str,
        run_id: str | None,
        event_type: str,
        request_id: str,
        previous_status: str | None,
        next_status: str | None,
        payload: Mapping[str, Any] | None,
    ):
        raise NotImplementedError

    def _require_run_locked(self, run_id: str) -> CodingTaskRun:
        raise NotImplementedError

    def _refresh_task_status_locked(self, task_id: str) -> None:
        raise NotImplementedError

    def create_approval(
        self, approval: ApprovalRequest, *, request_id: str
    ) -> ApprovalRequest:
        """Persist a pending approval and its audit event in one transaction."""

        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("new approval requests must be pending")
        with self._transaction():
            self._connection.execute(
                """INSERT INTO coding_approval_requests
                   (id, task_id, run_id, approval_type, requested_scope_json, reason,
                    status, expires_at, decided_at, decision_source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval.id,
                    approval.task_id,
                    approval.run_id,
                    approval.approval_type,
                    dump_json(approval.requested_scope),
                    approval.reason,
                    approval.status,
                    approval.expires_at,
                    approval.decided_at,
                    approval.decision_source,
                    approval.created_at,
                ),
            )
            self._append_event_locked(
                task_id=approval.task_id,
                run_id=approval.run_id,
                event_type="approval_requested",
                request_id=request_id,
                previous_status=None,
                next_status=ApprovalStatus.PENDING,
                payload={"approval_id": approval.id, "type": approval.approval_type},
            )
            return approval

    def get_pending_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return a pending approval by ID, excluding already decided requests."""

        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM coding_approval_requests
                   WHERE id = ? AND status = ?""",
                (approval_id, ApprovalStatus.PENDING),
            ).fetchone()
            return row_to_approval(row) if row else None

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return an approval request by ID regardless of decision state."""

        with self._lock:
            return self._get_approval_locked(approval_id)

    def list_approvals(
        self, *, status: ApprovalStatus | str | None = None
    ) -> list[ApprovalRequest]:
        """List approval requests, optionally filtered by lifecycle state."""

        query = "SELECT * FROM coding_approval_requests"
        values: tuple[ApprovalStatus, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            values = (ApprovalStatus(status),)
        query += " ORDER BY created_at, id"
        with self._lock:
            rows = self._connection.execute(query, values).fetchall()
            return [row_to_approval(row) for row in rows]

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        """Return all durable approvals that startup recovery must restore."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM coding_approval_requests
                   WHERE status = ? ORDER BY created_at, id""",
                (ApprovalStatus.PENDING,),
            ).fetchall()
            return [row_to_approval(row) for row in rows]

    def decide_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        decision_source: str,
        request_id: str,
    ) -> ApprovalRequest:
        """Resolve a pending approval exactly once and append the decision event."""

        if status is ApprovalStatus.PENDING:
            raise ValueError("approval decision must be terminal")
        with self._transaction():
            current = self._get_approval_locked(approval_id)
            if current is None:
                raise CodingAgentRecordNotFound(f"approval not found: {approval_id}")
            if current.status is not ApprovalStatus.PENDING:
                if current.status is status:
                    return current
                raise ValueError(f"approval already decided: {current.status}")
            decided_at = utc_now()
            self._connection.execute(
                """UPDATE coding_approval_requests
                   SET status = ?, decided_at = ?, decision_source = ? WHERE id = ?""",
                (status, decided_at, decision_source, approval_id),
            )
            self._append_event_locked(
                task_id=current.task_id,
                run_id=current.run_id,
                event_type=f"approval_{status}",
                request_id=request_id,
                previous_status=current.status,
                next_status=status,
                payload={"approval_id": approval_id, "decision_source": decision_source},
            )
            decided = self._get_approval_locked(approval_id)
            assert decided is not None
            return decided

    def resolve_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        decision_source: str,
        request_id: str,
        run_next_status: RunStatus | None = None,
        run_event_type: str = "approval_resolved",
        error_code: str | None = None,
        error_message: str | None = None,
        followup: ApprovalRequest | None = None,
    ) -> tuple[ApprovalRequest, CodingTaskRun | None, ApprovalRequest | None]:
        """Atomically decide approval, transition its Run and add a follow-up gate."""

        if status is ApprovalStatus.PENDING:
            raise ValueError("approval decision must be terminal")
        with self._transaction():
            current = self._get_approval_locked(approval_id)
            if current is None or current.status is not ApprovalStatus.PENDING:
                raise CodingAgentRecordNotFound(
                    f"pending approval not found: {approval_id}"
                )
            decided_at = utc_now()
            self._connection.execute(
                """UPDATE coding_approval_requests
                   SET status = ?, decided_at = ?, decision_source = ? WHERE id = ?""",
                (status, decided_at, decision_source, approval_id),
            )
            self._append_event_locked(
                task_id=current.task_id,
                run_id=current.run_id,
                event_type=f"approval_{status}",
                request_id=request_id,
                previous_status=current.status,
                next_status=status,
                payload={"approval_id": approval_id, "decision_source": decision_source},
            )
            run: CodingTaskRun | None = None
            if run_next_status is not None:
                if current.run_id is None:
                    raise ValueError("approval has no run")
                run = self._require_run_locked(current.run_id)
                require_run_transition(run.status, run_next_status)
                finished_at = (
                    utc_now() if run_next_status in TERMINAL_RUN_STATUSES else None
                )
                self._connection.execute(
                    """UPDATE coding_task_runs
                       SET status = ?, finished_at = COALESCE(?, finished_at),
                           error_code = ?, error_message = ? WHERE id = ?""",
                    (
                        run_next_status,
                        finished_at,
                        error_code,
                        error_message,
                        run.id,
                    ),
                )
                self._append_event_locked(
                    task_id=current.task_id,
                    run_id=run.id,
                    event_type=run_event_type,
                    request_id=request_id,
                    previous_status=run.status,
                    next_status=run_next_status,
                    payload={"approval_id": approval_id},
                )
                self._refresh_task_status_locked(current.task_id)
                run = self._require_run_locked(run.id)
            if followup is not None:
                if (
                    followup.task_id != current.task_id
                    or followup.run_id != current.run_id
                    or followup.status is not ApprovalStatus.PENDING
                ):
                    raise ValueError("follow-up approval must target the same Task/Run")
                self._connection.execute(
                    """INSERT INTO coding_approval_requests
                       (id, task_id, run_id, approval_type, requested_scope_json,
                        reason, status, expires_at, decided_at, decision_source,
                        created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        followup.id,
                        followup.task_id,
                        followup.run_id,
                        followup.approval_type,
                        dump_json(followup.requested_scope),
                        followup.reason,
                        followup.status,
                        followup.expires_at,
                        followup.decided_at,
                        followup.decision_source,
                        followup.created_at,
                    ),
                )
                self._append_event_locked(
                    task_id=followup.task_id,
                    run_id=followup.run_id,
                    event_type="approval_requested",
                    request_id=request_id,
                    previous_status=None,
                    next_status=ApprovalStatus.PENDING,
                    payload={
                        "approval_id": followup.id,
                        "type": followup.approval_type,
                    },
                )
            decided = self._get_approval_locked(approval_id)
            assert decided is not None
            return decided, run, followup

    def cancel_run_with_approvals(
        self,
        run_id: str,
        *,
        request_id: str,
        decision_source: str,
    ) -> CodingTaskRun:
        """Atomically revoke pending gates and cancel a non-running Run."""

        with self._transaction():
            run = self._require_run_locked(run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            if run.status is RunStatus.RUNNING:
                raise ValueError("running Run must stop its process before cancellation")
            approvals = self._connection.execute(
                """SELECT * FROM coding_approval_requests
                   WHERE run_id = ? AND status = ?""",
                (run_id, ApprovalStatus.PENDING),
            ).fetchall()
            decided_at = utc_now()
            for row in approvals:
                approval = row_to_approval(row)
                self._connection.execute(
                    """UPDATE coding_approval_requests SET status = ?, decided_at = ?,
                       decision_source = ? WHERE id = ?""",
                    (
                        ApprovalStatus.REVOKED,
                        decided_at,
                        decision_source,
                        approval.id,
                    ),
                )
                self._append_event_locked(
                    task_id=run.task_id,
                    run_id=run.id,
                    event_type="approval_revoked",
                    request_id=request_id,
                    previous_status=ApprovalStatus.PENDING,
                    next_status=ApprovalStatus.REVOKED,
                    payload={"approval_id": approval.id},
                )
            require_run_transition(run.status, RunStatus.CANCELLED)
            self._connection.execute(
                """UPDATE coding_task_runs SET status = ?, finished_at = ?,
                   error_code = ?, error_message = ? WHERE id = ?""",
                (
                    RunStatus.CANCELLED,
                    utc_now(),
                    "cancelled",
                    "用户请求取消",
                    run.id,
                ),
            )
            self._append_event_locked(
                task_id=run.task_id,
                run_id=run.id,
                event_type="cancelled",
                request_id=request_id,
                previous_status=run.status,
                next_status=RunStatus.CANCELLED,
                payload=None,
            )
            self._refresh_task_status_locked(run.task_id)
            return self._require_run_locked(run.id)

    def _get_approval_locked(self, approval_id: str) -> ApprovalRequest | None:
        row = self._connection.execute(
            "SELECT * FROM coding_approval_requests WHERE id = ?", (approval_id,)
        ).fetchone()
        return row_to_approval(row) if row else None

    create_coding_approval = create_approval
    get_coding_approval = get_approval
    list_coding_approvals = list_approvals
    decide_coding_approval = decide_approval
