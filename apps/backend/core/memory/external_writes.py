"""群环境层群笔记与成员层档案的写入互斥与整理提交时的乐观校验（#499）。

群笔记与成员档案有两个写入方：记忆整理（先读快照、调模型、提交时写回，耗时长）和
小手机里用户的编辑。整理不对准备阶段加锁，而是记下准备时读到的内容
（``ExternalLayerSnapshot``），提交时在短暂的写入互斥里比对：任一份被改过就整次
放弃（``commit_external_layers`` 返回 False），由整理按过期处理、下次用新快照重来。
小手机的写入只持同一把短锁（``EXTERNAL_MEMORY_WRITE_LOCK``），不等整理的长流程。
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.memory.member_profiles import (
    MemberKey,
    MemberProfile,
    MemberProfiles,
    MemberProfileUpdate,
)

# 群笔记与成员档案的写入互斥，进程内所有写入方共用，只在比对与落盘的瞬间持有；
# 整理之外的写入方（小手机）在其中读改写。
EXTERNAL_MEMORY_WRITE_LOCK = threading.Lock()


def _no_notes() -> dict[str, str]:
    return {}


def _no_profiles() -> dict[MemberKey, MemberProfile | None]:
    return {}


@dataclass(frozen=True)
class ExternalLayerSnapshot:
    """整理准备时读到、且本次会写回的群笔记与成员档案。

    ``group_notes`` 按会话 ID 记群笔记正文（没有时为空串）；``member_profiles``
    按成员记档案（没有时为 None）。只记本次更新会写的那些，其余的被改动不影响提交。
    """

    group_notes: Mapping[str, str] = field(default_factory=_no_notes)
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
        for thread_id, note in snapshot.group_notes.items():
            if group_environment.read_note(role_id, thread_id) != note:
                return False
        for key, profile in snapshot.member_profiles.items():
            if members.read(role_id, key) != profile:
                return False
        for update in environment_updates:
            group_environment.apply(role_id, update, updated_at=updated_at)
        for update in member_updates:
            members.apply(role_id, update)
    return True
