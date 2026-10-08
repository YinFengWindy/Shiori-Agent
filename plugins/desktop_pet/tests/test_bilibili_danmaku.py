"""DANMU_MSG parsing on the field layout captured from a live room (2026-10)."""

import json

import pytest

from plugins.desktop_pet.backend.bilibili_danmaku import (
    AnonymousDanmaku,
    Danmaku,
    DanmakuFormatError,
    parse_danmaku,
)


def danmu(
    *, cmd="DANMU_MSG", text="主播好", uid=7, uname="小明", dm_type=0, extra=None
):
    meta = [0, 1, 25, 16777215, 1, 2, 0, "hash", 0, 0, 0, "", dm_type, "{}", "{}"]
    extra = {"id_str": "abc123", "dm_type": dm_type} if extra is None else extra
    meta.append({"mode": 0, "extra": json.dumps(extra)})
    return {
        "cmd": cmd,
        "info": [
            meta,
            text,
            [uid, uname, 0],
            [],
            [],
            [],
            0,
            0,
            None,
            {"ts": 1, "ct": "X"},
        ],
    }


def test_plain_text_danmaku_carries_platform_id_and_full_identity():
    expected = Danmaku(message_id="abc123", uid=7, uname="小明", text="主播好")
    assert parse_danmaku(danmu()) == expected
    assert parse_danmaku(danmu(cmd="DANMU_MSG:4:0:2:2:2:0")) == expected


def test_other_commands_mirrors_and_emoticons_are_not_viewer_text():
    assert parse_danmaku({"cmd": "SEND_GIFT", "data": {}}) is None
    assert parse_danmaku(danmu(cmd="DANMU_MSG_MIRROR")) is None
    assert parse_danmaku(danmu(dm_type=1)) is None
    assert parse_danmaku(danmu(text="  ")) is None


def test_masked_sender_means_the_login_is_not_in_effect():
    with pytest.raises(AnonymousDanmaku):
        parse_danmaku(danmu(uid=0, uname="小***"))


def test_missing_message_id_is_a_format_error():
    with pytest.raises(DanmakuFormatError, match="id_str"):
        parse_danmaku(danmu(extra={"dm_type": 0}))
    with pytest.raises(DanmakuFormatError):
        parse_danmaku({"cmd": "DANMU_MSG", "info": []})


def test_blank_ids_or_names_are_format_errors_not_turns():
    with pytest.raises(DanmakuFormatError, match="id_str"):
        parse_danmaku(danmu(extra={"id_str": "  "}))
    with pytest.raises(DanmakuFormatError, match="发送者"):
        parse_danmaku(danmu(uname=" "))
