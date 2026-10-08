"""好感度状态与历史的持久化服务，是读写好感的唯一入口。

状态存于 ``<workspace>/roles/<role_id>/state/affection.json``（原子写入，文件存在即已初始化）；
历史逐行追加到同目录的 ``affection_history.jsonl``，全部保留。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from shiori_sdk.files.json import atomic_save_json

from .affection import (
    AffectionHistoryEntry,
    AffectionState,
    apply_affection_delta,
)
from .loneliness import _now_iso

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
        """Returns the display summary, or ``None`` while the role is uninitialized."""
        state = self.read_state(role_id)
        return state.summary() if state is not None else None

    def read_history(self, role_id: str) -> list[AffectionHistoryEntry]:
        """Returns every history entry in append (oldest-first) order."""
        path = self.history_path(role_id)
        if not path.exists():
            return []
        return [
            AffectionHistoryEntry(**json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def initialize(
        self,
        role_id: str,
        *,
        value: int,
        reason: str,
        now: datetime | None = None,
    ) -> AffectionState:
        """Creates the initial state and its ``init`` entry; initializing twice is an error."""
        at = _now_iso(now)
        with _WRITE_LOCK:
            if self.read_state(role_id) is not None:
                raise RuntimeError(f"角色好感度已初始化: {role_id}")
            state = AffectionState.initial(role_id, value=value, at=at)
            entry = AffectionHistoryEntry(at, None, state.value, None, reason, "init")
            self._commit(state, entry)
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
        at = _now_iso(now)
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
            self._commit(state, entry)
        return state

    def _commit(self, state: AffectionState, entry: AffectionHistoryEntry) -> None:
        # History goes first so a persisted value always has the entry explaining it.
        history = self.history_path(state.role_id)
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        atomic_save_json(
            self.state_path(state.role_id), state.to_dict(), domain="role.affection"
        )

    def _state_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / str(role_id).strip() / "state"
