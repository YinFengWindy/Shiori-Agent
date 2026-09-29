from __future__ import annotations

from pathlib import Path

import pytest

from core.accounts import AccountRecord
from core.common.message_source import MessageSource
from core.identity import BoundUserSenders, UserIdentity
from core.memory.member_profiles import (
    MEMBER_PROMPT_CHAR_LIMIT,
    MemberKey,
    MemberProfile,
    MemberProfileUpdate,
    MemberProfiles,
    render_member_profiles,
)

_QQ_555 = MemberKey("qq", "555")
_NO_BINDINGS = BoundUserSenders(identities=(), accounts=())


def test_same_channel_merges_across_groups_and_keeps_nickname_history(
    tmp_path: Path,
) -> None:
    members = MemberProfiles(tmp_path)

    members.apply(
        "mira",
        MemberProfileUpdate(
            _QQ_555, "g1", ("阿明",), profile="## 印象\n爱狗", brief="阿明：爱狗"
        ),
    )
    members.apply("mira", MemberProfileUpdate(_QQ_555, "g2", ("明哥",)))
    members.apply("mira", MemberProfileUpdate(_QQ_555, "g1", ("阿明",)))
    members.apply(
        "mira", MemberProfileUpdate(MemberKey("telegram", "555"), "t1", ("Ming",))
    )

    profile = members.read("mira", _QQ_555)
    assert profile is not None
    # 两个群的发言归同一份档案；旧昵称全保留，最近用的是称呼。
    assert profile.nicknames == ("明哥", "阿明")
    assert profile.call_name == "阿明"
    assert profile.thread_ids == ("g1", "g2")
    # 没有新内容的更新保留模型写过的档案与速记。
    assert profile.profile == "## 印象\n爱狗"
    assert profile.brief == "阿明：爱狗"
    # 不同渠道的相同 ID 是另一份档案。
    other = members.read("mira", MemberKey("telegram", "555"))
    assert other is not None and other.nicknames == ("Ming",)
    assert members.profile_path("mira", _QQ_555) != members.profile_path(
        "mira", MemberKey("telegram", "555")
    )
    assert [item.key for item in members.list("mira", thread_id="g2")] == [_QQ_555]
    assert len(members.list("mira")) == 2


def test_write_and_delete_one_profile(tmp_path: Path) -> None:
    members = MemberProfiles(tmp_path)
    edited = MemberProfile(_QQ_555, ("阿明",), ("g1",), "阿明：改过", "## 印象\n改过")

    members.write("mira", edited)
    assert members.read("mira", _QQ_555) == edited

    members.delete("mira", _QQ_555)
    assert members.read("mira", _QQ_555) is None
    with pytest.raises(FileNotFoundError):
        members.delete("mira", _QQ_555)


def _source(sender_id: str, **fields: object) -> MessageSource:
    return MessageSource(channel="qq", sender_id=sender_id, **fields)  # type: ignore[arg-type]


def _save(members: MemberProfiles, sender_id: str, brief_len: int = 20) -> None:
    members.write(
        "mira",
        MemberProfile(
            MemberKey("qq", sender_id),
            (f"人{sender_id}",),
            ("g1",),
            brief=f"速记{sender_id}" + "。" * brief_len,
            profile=f"完整档案{sender_id}",
        ),
    )


def test_trigger_and_its_mention_and_reply_targets_get_full_profiles(
    tmp_path: Path,
) -> None:
    members = MemberProfiles(tmp_path)
    for sender_id in ("1", "2", "3", "4", "5"):
        _save(members, sender_id)

    rendered = render_member_profiles(
        members,
        "mira",
        trigger=_source("1", mentioned_ids=("2",), reply_to_sender_id="3"),
        # 4 在窗口里发过言；5 在窗口里被结构化 @ 到；用户本人不进入。
        window=(
            _source("4"),
            _source("1", mentioned_ids=("5",)),
            _source("9", sender_is_user=True),
        ),
        bound=_NO_BINDINGS,
    )

    for full in ("1", "2", "3"):
        assert f"完整档案{full}" in rendered
        assert f"速记{full}" not in rendered
    for brief in ("4", "5"):
        assert f"速记{brief}" in rendered
        assert f"完整档案{brief}" not in rendered


def test_briefs_are_trimmed_from_the_longest_silent_speaker(tmp_path: Path) -> None:
    members = MemberProfiles(tmp_path)
    for index in range(80):
        _save(members, str(index))

    rendered = render_member_profiles(
        members,
        "mira",
        trigger=_source("0"),
        # 旧的在前：79 最近发过言。
        window=tuple(_source(str(index)) for index in range(1, 80)),
        bound=_NO_BINDINGS,
    )

    assert len(rendered) <= MEMBER_PROMPT_CHAR_LIMIT
    assert "完整档案0" in rendered
    assert "速记79" in rendered
    assert "速记1。" not in rendered
    kept = [index for index in range(1, 80) if f"速记{index}。" in rendered]
    assert kept == list(range(kept[0], 80))


def test_user_as_trigger_gets_no_profile(tmp_path: Path) -> None:
    members = MemberProfiles(tmp_path)
    _save(members, "9")

    rendered = render_member_profiles(
        members,
        "mira",
        trigger=_source("9", sender_is_user=True),
        window=(),
        bound=_NO_BINDINGS,
    )

    assert rendered == ""


def test_members_bound_to_the_user_now_are_not_injected(tmp_path: Path) -> None:
    members = MemberProfiles(tmp_path)
    for sender_id in ("7", "8"):
        _save(members, sender_id)
    # 档案建于绑定之前；此刻 7 已绑定为用户本人，消息却没有标记。
    bound = BoundUserSenders(
        identities=(
            UserIdentity("i1", "qq", "7", "platform", "", "2026-09-30T00:00:00"),
        ),
        accounts=(AccountRecord("qq:1", "qq", "qq", "1", "cfg", role_id="mira"),),
    )

    rendered = render_member_profiles(
        members, "mira", trigger=_source("7"), window=(_source("8"),), bound=bound
    )

    assert "完整档案7" not in rendered and "速记7" not in rendered
    assert "速记8" in rendered


def test_malformed_profile_header_fails_with_a_clear_error(tmp_path: Path) -> None:
    members = MemberProfiles(tmp_path)
    path = members.profile_path("mira", _QQ_555)
    path.parent.mkdir(parents=True)
    path.write_text(
        '---\n{"channel": "qq", "sender_id": "555", "nicknames": "阿明",'
        ' "thread_ids": [], "brief": ""}\n---\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="nicknames 必须是文本列表"):
        members.read("mira", _QQ_555)
