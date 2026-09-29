"""成员层：角色对外部会话里群友、陌生人的成员档案（#498）。

- 成员以「渠道 + 发送者 ID」识别（``MemberKey``）：同一渠道里在不同群的发言归同一人，
  不同渠道的相同 ID 是两个人。已绑定用户本人不建成员档案。
- 每个成员一份 Markdown（角色记忆目录下的 ``memory/members/``）：开头是宿主维护的
  JSON 头（渠道、成员 ID、昵称历史、出现过的会话、一行速记），其后是完整档案正文
  （印象、他说过的关于自己的事、与我的互动要点）。
- 昵称历史与出现过的会话由宿主从消息来源快照累积，不靠模型；完整档案与速记由
  记忆整理的外部段产出。二者都由宿主写入，不经过记忆引擎。
- 外部上下文回合按分层注入当前窗口相关成员的档案（``render_member_profiles``）；
  用户上下文回合不注入。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from core.common.message_source import MessageSource
from utils.helpers import ensure_dir

# 完整档案正文的固定小节与篇幅上限（整篇字数，注入时原样使用，不再截取）。
MEMBER_PROFILE_SECTIONS = ("印象", "他说过的自己", "与我的互动")
MEMBER_PROFILE_CHAR_LIMIT = 150
# 一行速记的篇幅：称呼 + 一句最关键的印象，由模型概括，不从档案截取。
MEMBER_BRIEF_CHAR_LIMIT = 30
# 外部回合注入的成员档案段落合计字数上限；超出时按最近发言先后裁掉速记。
MEMBER_PROMPT_CHAR_LIMIT = 1500

_HEADER_FENCE = "---"
_UNSAFE_FILENAME_CHARS = re.compile(r"[^0-9A-Za-z._-]+")


@dataclass(frozen=True)
class MemberKey:
    """成员的归属键：渠道 + 发送者 ID。"""

    channel: str
    sender_id: str

    @classmethod
    def from_source(cls, source: MessageSource) -> MemberKey | None:
        """消息来源对应的成员；渠道或发送者未知时为 None（无从识别）。"""
        if not source.channel or not source.sender_id:
            return None
        return cls(channel=source.channel, sender_id=source.sender_id)


@dataclass(frozen=True)
class MemberProfile:
    """一个成员的档案。

    ``nicknames`` 是出现过的全部昵称快照，按最近一次使用排序，最后一个是当前称呼；
    ``thread_ids`` 是该成员发过言的会话，供按会话列出成员；``brief`` 是一行速记，
    ``profile`` 是完整档案正文。
    """

    key: MemberKey
    nicknames: tuple[str, ...] = ()
    thread_ids: tuple[str, ...] = ()
    brief: str = ""
    profile: str = ""

    @property
    def call_name(self) -> str:
        """称呼：最近的昵称快照；从未记下昵称时用成员 ID。"""
        return self.nicknames[-1] if self.nicknames else self.key.sender_id


@dataclass(frozen=True)
class MemberProfileUpdate:
    """一次整理为某个成员产出的更新。

    ``thread_id`` 与 ``nicknames``（本次在该会话里见到的昵称，按出现先后）由宿主从
    消息来源得出；``profile`` / ``brief`` 来自模型，为空时保留原有内容。
    """

    key: MemberKey
    thread_id: str
    nicknames: tuple[str, ...]
    profile: str = ""
    brief: str = ""


def merge_member_profile(
    existing: MemberProfile | None, update: MemberProfileUpdate
) -> MemberProfile:
    """在 ``existing`` 上合并一次更新：昵称与会话只增不减，档案与速记非空才替换。

    再次用到的旧昵称移到末尾，使最后一个始终是最近的称呼。
    """
    base = existing if existing is not None else MemberProfile(key=update.key)
    nicknames = list(base.nicknames)
    for name in update.nicknames:
        if name in nicknames:
            nicknames.remove(name)
        nicknames.append(name)
    thread_ids = tuple(dict.fromkeys((*base.thread_ids, update.thread_id)))
    return replace(
        base,
        nicknames=tuple(nicknames),
        thread_ids=thread_ids,
        profile=update.profile or base.profile,
        brief=update.brief or base.brief,
    )


class MemberProfiles:
    """成员档案的存储：角色记忆目录下按成员一个 Markdown 文件。

    只依赖工作区路径，读写直接落盘，不持有状态，需要的地方各自构造即可。
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    def profile_path(self, role_id: str, key: MemberKey) -> Path:
        """成员的档案文件；文件名由渠道与成员 ID 转成安全字符并加短哈希。"""
        raw = f"{key.channel}:{key.sender_id}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        stem = _UNSAFE_FILENAME_CHARS.sub("_", raw).strip("_")
        return self._members_dir(role_id) / f"{stem}-{digest}.md"

    def read(self, role_id: str, key: MemberKey) -> MemberProfile | None:
        """成员的档案；还没有时为 None。"""
        path = self.profile_path(role_id, key)
        if not path.exists():
            return None
        return _parse_profile_file(path.read_text(encoding="utf-8"))

    def write(self, role_id: str, profile: MemberProfile) -> None:
        """整份写入成员档案（覆盖原有内容）。"""
        _ = ensure_dir(self._members_dir(role_id))
        _ = self.profile_path(role_id, profile.key).write_text(
            _render_profile_file(profile), encoding="utf-8"
        )

    def delete(self, role_id: str, key: MemberKey) -> None:
        """删除成员档案；档案不存在时抛 ``FileNotFoundError``。"""
        self.profile_path(role_id, key).unlink()

    def apply(self, role_id: str, update: MemberProfileUpdate) -> None:
        """把一次整理的更新合并进成员档案。"""
        self.write(
            role_id, merge_member_profile(self.read(role_id, update.key), update)
        )

    def list(self, role_id: str, *, thread_id: str = "") -> list[MemberProfile]:
        """角色的全部成员档案；给出 ``thread_id`` 时只列在该会话发过言的成员。"""
        members_dir = self._members_dir(role_id)
        if not members_dir.exists():
            return []
        profiles = [
            _parse_profile_file(path.read_text(encoding="utf-8"))
            for path in sorted(members_dir.glob("*.md"))
        ]
        if thread_id:
            profiles = [item for item in profiles if thread_id in item.thread_ids]
        return profiles

    def _members_dir(self, role_id: str) -> Path:
        clean_role_id = role_id.strip()
        if not clean_role_id:
            raise ValueError("role_id required for member profile access")
        return self._workspace / "roles" / clean_role_id / "memory" / "members"


def _render_profile_file(profile: MemberProfile) -> str:
    header = json.dumps(
        {
            "channel": profile.key.channel,
            "sender_id": profile.key.sender_id,
            "nicknames": list(profile.nicknames),
            "thread_ids": list(profile.thread_ids),
            "brief": profile.brief,
        },
        ensure_ascii=False,
        indent=2,
    )
    body = profile.profile.strip()
    return f"{_HEADER_FENCE}\n{header}\n{_HEADER_FENCE}\n\n{body}\n"


def _parse_profile_file(text: str) -> MemberProfile:
    """解析档案文件；JSON 头缺失或字段不对说明文件已损坏，直接抛错。"""
    lines = text.split("\n")
    if not lines or lines[0] != _HEADER_FENCE or _HEADER_FENCE not in lines[1:]:
        raise ValueError("成员档案缺少 JSON 头")
    end = lines.index(_HEADER_FENCE, 1)
    header = json.loads("\n".join(lines[1:end]))
    return MemberProfile(
        key=MemberKey(
            channel=str(header["channel"]), sender_id=str(header["sender_id"])
        ),
        nicknames=tuple(str(name) for name in header["nicknames"]),
        thread_ids=tuple(str(item) for item in header["thread_ids"]),
        brief=str(header["brief"]),
        profile="\n".join(lines[end + 1 :]).strip(),
    )


def _mentioned_keys(source: MessageSource) -> list[MemberKey]:
    """消息结构化 @ 到的成员；与发送者同一渠道。"""
    if not source.channel:
        return []
    return [
        MemberKey(channel=source.channel, sender_id=member_id)
        for member_id in source.mentioned_ids
    ]


def _full_profile_keys(trigger: MessageSource) -> list[MemberKey]:
    """注入完整档案的成员：触发本回合的发送者（用户本人除外），及其 @ / 回复的成员。"""
    keys: list[MemberKey] = []
    sender = MemberKey.from_source(trigger)
    if sender is not None and not trigger.sender_is_user:
        keys.append(sender)
    keys.extend(_mentioned_keys(trigger))
    if trigger.channel and trigger.reply_to_sender_id:
        keys.append(MemberKey(trigger.channel, trigger.reply_to_sender_id))
    return list(dict.fromkeys(keys))


def _brief_keys_by_recency(window: Sequence[MessageSource]) -> list[MemberKey]:
    """注入速记的候选：窗口里的发言者与被结构化 @ 到的成员，最近出现的在前。"""
    seen: dict[MemberKey, None] = {}
    for source in reversed(window):
        sender = MemberKey.from_source(source)
        if sender is not None and not source.sender_is_user:
            seen.setdefault(sender, None)
        for key in _mentioned_keys(source):
            seen.setdefault(key, None)
    return list(seen)


def _render_full_profile(profile: MemberProfile) -> str:
    lines = [f"### {profile.call_name}（ID {profile.key.sender_id}）"]
    if len(profile.nicknames) > 1:
        lines.append(f"用过的昵称：{'、'.join(profile.nicknames)}")
    lines.append(profile.profile)
    return "\n".join(lines)


def render_member_profiles(
    members: MemberProfiles,
    role_id: str,
    *,
    trigger: MessageSource,
    window: Sequence[MessageSource],
) -> str:
    """外部上下文回合注入的成员档案段落；没有可注入的档案时为空串。

    分两层：触发本回合的发送者及其 @ / 回复到的成员注入完整档案；窗口
    ``window``（本回合可见的外部历史里非用户本人消息的来源，旧的在前）中的其他
    发言者与被结构化 @ 到的成员注入一行速记。合计不超过 ``MEMBER_PROMPT_CHAR_LIMIT``
    字，超出时从最久没出现的成员起裁掉速记；完整档案不裁。没有档案的成员跳过。
    """
    full_keys = _full_profile_keys(trigger)
    full_parts = [
        _render_full_profile(profile)
        for key in full_keys
        if (profile := members.read(role_id, key)) is not None and profile.profile
    ]
    title = "## 我认得的群友"
    budget = (
        MEMBER_PROMPT_CHAR_LIMIT
        - len(title)
        - sum(len(part) + 2 for part in full_parts)
    )
    brief_lines: list[str] = []
    for key in _brief_keys_by_recency(window):
        if key in full_keys:
            continue
        profile = members.read(role_id, key)
        if profile is None or not profile.brief:
            continue
        line = f"- {profile.brief}（ID {key.sender_id}）"
        # 候选按最近出现排序，放不下时后面更久远的也一并裁掉。
        if len(line) + 1 > budget:
            break
        budget -= len(line) + 1
        brief_lines.append(line)
    if not full_parts and not brief_lines:
        return ""
    sections = [title, *full_parts]
    if brief_lines:
        sections.append("\n".join(brief_lines))
    return "\n\n".join(sections)
