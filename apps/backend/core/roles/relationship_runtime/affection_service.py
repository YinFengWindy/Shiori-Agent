"""好感度状态与历史的持久化服务，是读写好感的唯一入口。

状态存于 ``<workspace>/roles/<role_id>/state/affection.json``（原子写入，文件存在即已初始化）；
历史逐行追加到同目录的 ``affection_history.jsonl``，全部保留。
长时间未联系的衰减不靠定时任务写入，而是在读取摘要、心跳和用户发消息时
由 ``settle_decay`` 按需补算。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from shiori_sdk.files.json import atomic_save_json
from shiori_sdk.values import now_iso

from .affection import (
    AffectionHistoryEntry,
    AffectionState,
    apply_affection_delta,
    record_user_message,
    settle_affection_decay,
)

_STATE_FILE = "affection.json"
_HISTORY_FILE = "affection_history.jsonl"
# One process-wide gate: several service instances may share a workspace.
_WRITE_LOCK = threading.Lock()


class RoleAffectionService:
    """Reads and changes per-role affection; every change appends one history entry."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)

    def state_path(self, role_id: str) -> Path:
        """Returns the role's affection state file."""
        return self._state_root(role_id) / _STATE_FILE

    def history_path(self, role_id: str) -> Path:
        """Returns the role's append-only affection history file."""
        return self._state_root(role_id) / _HISTORY_FILE

    def read_state(self, role_id: str) -> AffectionState | None:
        """Returns the current state, or ``None`` while the role is uninitialized."""
        path = self.state_path(role_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"好感状态文件格式错误: {path}")
        return AffectionState.from_dict(payload)

    def summary(self, role_id: str) -> dict[str, Any] | None:
        """Returns the stored display summary without settling decay.

        ``None`` while the role is uninitialized. Display paths use
        ``current_summary`` so overdue decay shows up.
        """
        state = self.read_state(role_id)
        return state.summary() if state is not None else None

    def current_summary(
        self, role_id: str, *, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """Settles overdue decay (a write when any is due), then returns the summary."""
        state = self.settle_decay(role_id, now=now)
        return state.summary() if state is not None else None

    def settle_decay(
        self, role_id: str, *, now: datetime | None = None
    ) -> AffectionState | None:
        """Applies every decay step due by ``now`` (see ``settle_affection_decay``).

        Returns the settled state, or ``None`` while the role is uninitialized.
        """
        now_dt = (now or datetime.now()).astimezone()
        with _WRITE_LOCK:
            return self._settle_locked(role_id, now_dt)

    def record_user_activity(
        self, role_id: str, *, now: datetime | None = None
    ) -> AffectionState | None:
        """Restarts the decay timer for the user's own message.

        Decay already due by ``now`` is settled first, so a long absence still
        costs its overdue days. Callers pass only messages from the user; an
        uninitialized role has no timer and returns ``None``.
        """
        now_dt = (now or datetime.now()).astimezone()
        with _WRITE_LOCK:
            settled = self._settle_locked(role_id, now_dt)
            if settled is None:
                return None
            state = record_user_message(settled, at=now_dt.isoformat())
            self._commit(state, ())
        return state

    def read_history(self, role_id: str) -> list[AffectionHistoryEntry]:
        """Returns every history entry in append (oldest-first) order."""
        path = self.history_path(role_id)
        if not path.exists():
            return []
        entries: list[AffectionHistoryEntry] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"好感历史第 {number + 1} 行格式错误: {path}")
            entries.append(AffectionHistoryEntry.from_dict(payload))
        return entries

    def history_page(
        self, role_id: str, *, page: int, page_size: int
    ) -> tuple[list[tuple[int, AffectionHistoryEntry]], int]:
        """Returns one newest-first page of ``(id, entry)`` and the total count.

        An entry's id is its 0-based append position, stable because history
        is append-only. ``page`` is 1-based. The JSONL file is read in full on every call; it
        gains at most one line per turn or decay day, so that stays cheap for
        the history sizes a role accumulates.
        """
        if page < 1 or page_size < 1:
            raise ValueError("page 与 page_size 必须是正整数")
        newest_first = list(enumerate(self.read_history(role_id)))[::-1]
        start = (page - 1) * page_size
        return newest_first[start : start + page_size], len(newest_first)

    def initialize(
        self,
        role_id: str,
        *,
        value: int,
        reason: str,
        now: datetime | None = None,
    ) -> AffectionState:
        """Creates the initial state and its ``init`` entry; initializing twice is an error."""
        at = now.astimezone().isoformat() if now else now_iso()
        with _WRITE_LOCK:
            if self.read_state(role_id) is not None:
                raise RuntimeError(f"角色好感度已初始化: {role_id}")
            state = AffectionState.initial(role_id, value=value, at=at)
            entry = AffectionHistoryEntry(at, None, state.value, None, reason, "init")
            self._commit(state, (entry,))
        return state

    def apply_delta(
        self,
        role_id: str,
        *,
        delta: int,
        reason: str,
        source: Literal["turn", "decay"],
        now: datetime | None = None,
    ) -> AffectionState:
        """Applies one change through the shared clamp and stage-floor rule.

        History records the effective change; a change that the floor or the
        upper bound reduces to zero writes nothing.
        """
        at = now.astimezone().isoformat() if now else now_iso()
        with _WRITE_LOCK:
            current = self.read_state(role_id)
            if current is None:
                raise RuntimeError(f"角色好感度尚未初始化: {role_id}")
            state = apply_affection_delta(current, delta, at=at)
            # The floor only rises with the value, so an unchanged value is a no-op.
            if state.value == current.value:
                return current
            entry = AffectionHistoryEntry(
                at,
                current.value,
                state.value,
                state.value - current.value,
                reason,
                source,
            )
            self._commit(state, (entry,))
        return state

    def _settle_locked(self, role_id: str, now: datetime) -> AffectionState | None:
        current = self.read_state(role_id)
        if current is None:
            return None
        state, entries = settle_affection_decay(current, now=now)
        if state != current:
            self._commit(state, entries)
        return state

    def _commit(
        self, state: AffectionState, entries: Sequence[AffectionHistoryEntry]
    ) -> None:
        # State first: a failed state write leaves no entry behind, so a retried
        # initialization, change or settlement cannot record the same event twice.
        atomic_save_json(
            self.state_path(state.role_id), state.to_dict(), domain="role.affection"
        )
        if not entries:
            return
        history = self.history_path(state.role_id)
        with history.open("a", encoding="utf-8", newline="\n") as stream:
            stream.writelines(
                json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
                for entry in entries
            )

    def _state_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / str(role_id).strip() / "state"
