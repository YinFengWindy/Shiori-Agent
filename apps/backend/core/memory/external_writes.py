"""群环境层群笔记与成员层档案的写入互斥与整理提交时的乐观校验（#499）。

群环境与成员档案由记忆整理、小手机和角色工具写入。整理不对准备阶段加锁，
而是记下准备时读到的内容
（``ExternalLayerSnapshot``），提交时在短暂的写入互斥里比对：任一份被改过就整次
放弃（``commit_external_layers`` 返回 False），由整理按过期处理、下次用新快照重来。
小手机的写入只持同一把短锁（``EXTERNAL_MEMORY_WRITE_LOCK``），不等整理的长流程。
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.memory.group_environment import (
    GROUP_EDIT_REVISION_KEY,
    SUMMARY_LABEL_KEY,
    SUMMARY_UPDATED_AT_KEY,
    GroupEnvironment,
    GroupEnvironmentSnapshot,
    GroupEnvironmentUpdate,
)
from core.memory.member_profiles import (
    MemberKey,
    MemberProfile,
    MemberProfiles,
    MemberProfileUpdate,
)

# 群笔记与成员档案的写入互斥，进程内所有写入方共用，只在比对与落盘的瞬间持有；
# 整理之外的写入方（小手机）在其中读改写。
EXTERNAL_MEMORY_WRITE_LOCK = threading.Lock()


def _no_environments() -> dict[str, GroupEnvironmentSnapshot]:
    return {}


def _no_profiles() -> dict[MemberKey, MemberProfile | None]:
    return {}


@dataclass(frozen=True)
class ExternalLayerSnapshot:
    """整理准备时读到、且本次会写回的群环境与成员档案。

    ``group_environments`` 按会话记笔记、摘要、更新时间及手动编辑版本；即使编辑后
    又恢复原文，旧整理仍需重做。``member_profiles`` 按成员记档案（没有时为 None）。
    """

    group_environments: Mapping[str, GroupEnvironmentSnapshot] = field(
        default_factory=_no_environments
    )
    member_profiles: Mapping[MemberKey, MemberProfile | None] = field(
        default_factory=_no_profiles
    )


def commit_external_layers(
    group_environment: GroupEnvironment,
    members: MemberProfiles,
    role_id: str,
    *,
    environment_updates: Sequence[GroupEnvironmentUpdate],
    member_updates: Sequence[MemberProfileUpdate],
    snapshot: ExternalLayerSnapshot,
    updated_at: datetime,
) -> bool:
    """快照仍是当前内容时写入整理的更新并返回 True；任一份已被改过则什么都不写、返回 False。"""
    with EXTERNAL_MEMORY_WRITE_LOCK:
        for thread_id, environment in snapshot.group_environments.items():
            if group_environment.read(role_id, thread_id) != environment:
                return False
        for key, profile in snapshot.member_profiles.items():
            if members.read(role_id, key) != profile:
                return False
        for update in environment_updates:
            group_environment.apply(role_id, update, updated_at=updated_at)
        for update in member_updates:
            members.apply(role_id, update)
    return True


def edit_group_environment(
    environment: GroupEnvironment,
    role_id: str,
    thread_id: str,
    *,
    group_note: str | None = None,
    summary: str | None = None,
    label: str,
    updated_at: datetime,
) -> GroupEnvironmentSnapshot:
    """Edits supplied fields under the consolidation lock; empty text clears a field.

    Every real edit advances the persistent revision, even if the text later returns
    to its old value. No-op edits do not write. Summary/revision roll back on a note
    failure; a database commit failure restores the old note.
    """
    with EXTERNAL_MEMORY_WRITE_LOCK:
        previous = environment.read(role_id, thread_id)
        next_note = previous.group_note if group_note is None else group_note.strip()
        next_summary = previous.recent_activity if summary is None else summary.strip()
        note_changed = next_note != previous.group_note
        summary_changed = next_summary != previous.recent_activity
        if not note_changed and not summary_changed:
            return previous
        metadata: dict[str, Any] = {
            GROUP_EDIT_REVISION_KEY: previous.edit_revision + 1,
        }
        if summary_changed:
            metadata.update(
                {
                    SUMMARY_UPDATED_AT_KEY: updated_at.isoformat(),
                    SUMMARY_LABEL_KEY: label,
                }
            )
        note_saved = False
        try:
            with environment.conversation_store.state_transaction():
                _ = environment.conversation_store.upsert_thread_state(
                    thread_id,
                    summary=next_summary if summary_changed else None,
                    metadata=metadata,
                )
                if note_changed:
                    environment.write_note(role_id, thread_id, next_note)
                    note_saved = True
        except Exception as error:
            if note_saved:
                try:
                    environment.write_note(role_id, thread_id, previous.group_note)
                except Exception as restore_error:
                    raise ExceptionGroup(
                        "群环境修改失败且群笔记恢复失败，请检查群笔记当前内容",
                        [error, restore_error],
                    ) from error
            raise
        return environment.read(role_id, thread_id)
