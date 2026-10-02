"""群环境层：角色对每个外部会话（群聊、陌生私聊）的最近动态与群笔记（#497）。

- 最近动态：写在会话状态（``thread_state``）的 ``summary`` 字段，一两句话，
  更新时间与会话称呼记在同一行的 metadata 里。
- 群笔记：角色记忆目录下按会话一个的 Markdown（``memory/groups/``），记群的
  氛围、常聊话题、角色在群里的定位与重要事件。

二者都由宿主在记忆整理提交时写入，不经过记忆引擎。用户上下文回合（含主动、
发呆）注入最近 ``RECENT_ACTIVITY_WINDOW`` 内更新过的最近动态，至多
``RECENT_ACTIVITY_LIMIT`` 个；外部上下文回合注入当前会话的群笔记，以及其他外部
会话的最近动态（同样的时间窗与上限，不含当前会话，#539）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from conversation.context_scope import load_user_context_threads
from conversation.store import ConversationStore
from core.memory.role_paths import keyed_markdown_name, role_memory_dir
from shiori_sdk.files.text import atomic_save_text

# 用户上下文注入最近动态的时间窗与数量上限。
RECENT_ACTIVITY_WINDOW = timedelta(days=3)
RECENT_ACTIVITY_LIMIT = 5
# thread_state.metadata 里与最近动态一同写入的字段。
SUMMARY_UPDATED_AT_KEY = "summary_updated_at"
SUMMARY_LABEL_KEY = "summary_label"
# 手动编辑的持久版本，不依赖正文或笔记文件是否存在；用于拒绝编辑前准备的整理。
GROUP_EDIT_REVISION_KEY = "group_edit_revision"


@dataclass(frozen=True)
class GroupEnvironmentUpdate:
    """一次整理为某个外部会话产出的群环境层更新。

    ``label`` 是会话的称呼（如 ``群「猫猫群」``）；``recent_activity`` 与
    ``group_note`` 为空时保留原有内容。
    """

    thread_id: str
    label: str
    recent_activity: str
    group_note: str


@dataclass(frozen=True)
class GroupEnvironmentSnapshot:
    """群环境正文、摘要时间及手动编辑版本；缺失正文/时间为空串，版本默认为 0。"""

    recent_activity: str
    group_note: str
    summary_updated_at: str = ""
    edit_revision: int = 0


@dataclass(frozen=True)
class RecentActivity:
    """一个外部会话的最近动态。"""

    thread_id: str
    label: str
    summary: str
    updated_at: datetime


class GroupEnvironment:
    """群环境层的存储：最近动态在 ``ConversationStore``，群笔记在角色记忆目录。"""

    def __init__(self, workspace: Path, conversation_store: ConversationStore) -> None:
        self._workspace = workspace
        self._store = conversation_store

    @property
    def conversation_store(self) -> ConversationStore:
        """最近动态所在的会话存储；提示块也从这里读旁听记录与群里的消息（#539）。"""
        return self._store

    def note_path(self, role_id: str, thread_id: str) -> Path:
        """会话 ``thread_id`` 的群笔记文件；文件名由会话 ID 转成安全字符并加短哈希。"""
        return self._groups_dir(role_id) / keyed_markdown_name(thread_id)

    def read_note(self, role_id: str, thread_id: str) -> str:
        """会话的群笔记；还没有时为空串。"""
        path = self.note_path(role_id, thread_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def write_note(self, role_id: str, thread_id: str, note: str) -> None:
        """整篇原子覆盖会话的群笔记（中断时保留旧文件）；内容为空时删除笔记文件。"""
        text = note.strip()
        path = self.note_path(role_id, thread_id)
        if not text:
            path.unlink(missing_ok=True)
            return
        atomic_save_text(path, text + "\n")

    def read(self, role_id: str, thread_id: str) -> GroupEnvironmentSnapshot:
        """会话当前的最近动态与群笔记。"""
        state = self._store.get_thread_state(thread_id)
        return GroupEnvironmentSnapshot(
            recent_activity=state.summary if state is not None else "",
            group_note=self.read_note(role_id, thread_id),
            summary_updated_at=(
                str(state.metadata.get(SUMMARY_UPDATED_AT_KEY) or "")
                if state is not None
                else ""
            ),
            edit_revision=(
                int(state.metadata.get(GROUP_EDIT_REVISION_KEY, 0))
                if state is not None
                else 0
            ),
        )

    def apply(
        self, role_id: str, update: GroupEnvironmentUpdate, *, updated_at: datetime
    ) -> None:
        """写入一次整理的产出；空字段保留原有内容。"""
        if update.recent_activity:
            self._store.upsert_thread_state(
                update.thread_id,
                summary=update.recent_activity,
                metadata={
                    SUMMARY_UPDATED_AT_KEY: updated_at.isoformat(),
                    SUMMARY_LABEL_KEY: update.label,
                },
            )
        if update.group_note:
            self.write_note(role_id, update.thread_id, update.group_note)

    def recent_activities(
        self, role_id: str, *, now: datetime, exclude_thread_id: str = ""
    ) -> list[RecentActivity]:
        """``now`` 之前 ``RECENT_ACTIVITY_WINDOW`` 内更新过的外部会话最近动态，新的在前。

        按此刻的身份绑定跳过已属于用户上下文的会话（例如陌生私聊绑定后并入）：
        它们的记录不迁移也不删除，只是不再作为外部会话的动态注入。外部回合用
        ``exclude_thread_id`` 跳过自己所在的会话，上限只数其他会话。
        """
        user_threads = load_user_context_threads(self._workspace, role_id)
        activities: list[RecentActivity] = []
        for state in self._store.list_summarized_thread_states(role_id):
            if (
                user_threads.contains(state.owner_id)
                or state.owner_id == exclude_thread_id
            ):
                continue
            # ``apply`` 总是把摘要与更新时间一起写入；有摘要却缺时间说明数据已损坏，
            # 直接 KeyError 失败即停，不猜一个时间。
            updated_at = datetime.fromisoformat(
                str(state.metadata[SUMMARY_UPDATED_AT_KEY])
            )
            if now - updated_at > RECENT_ACTIVITY_WINDOW:
                continue
            activities.append(
                RecentActivity(
                    thread_id=state.owner_id,
                    label=str(state.metadata.get(SUMMARY_LABEL_KEY) or ""),
                    summary=state.summary,
                    updated_at=updated_at,
                )
            )
        activities.sort(key=lambda item: item.updated_at, reverse=True)
        return activities[:RECENT_ACTIVITY_LIMIT]

    def render_recent_activity(
        self, role_id: str, *, now: datetime, current_thread_id: str = ""
    ) -> str:
        """「各会话最近动态」段落；没有时为空串。

        用户上下文回合不给 ``current_thread_id``，列出全部外部会话；外部回合给出
        自己所在的会话，只列其他外部会话（#539）。
        """
        activities = self.recent_activities(
            role_id, now=now, exclude_thread_id=current_thread_id
        )
        if not activities:
            return ""
        title = (
            "## 我在其他群聊与私聊里的最近动态"
            if current_thread_id
            else "## 我在群聊与其他私聊里的最近动态"
        )
        lines = [
            title,
            "",
            *(
                f"- {item.label or '一个会话'}"
                f"（{item.updated_at.strftime('%m-%d %H:%M')} 更新）：{item.summary}"
                for item in activities
            ),
        ]
        return "\n".join(lines)

    def render_group_note(self, role_id: str, thread_id: str) -> str:
        """外部上下文回合注入的当前会话群笔记段落；没有时为空串。"""
        note = self.read_note(role_id, thread_id)
        if not note:
            return ""
        return f"## 我对这个会话的群笔记\n\n{note}"

    def _groups_dir(self, role_id: str) -> Path:
        return role_memory_dir(self._workspace, role_id) / "groups"
