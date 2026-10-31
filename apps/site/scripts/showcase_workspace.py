"""Builds the isolated desktop workspace one showcase still is captured from.

``stills.ts`` (beside this file) runs this with the repository ``.venv`` once per
still, then opens the real desktop app on the workspace it wrote. The role is
copied from a real workspace (``--source``): only its card and the pictures
the card references — name, profile, avatar, illustrations and the mood
bindings — never its chats, memories, affection or relationship state, which
are someone's private history. Everything the still shows besides the card
is demo data written here, dated relative to now so nothing on screen looks
stale and no decay or catch-up rewrites it at launch.

The model registration and the memory plugin's embedding endpoint point at a
closed loopback port: the app has a model to show and its memory plugin starts,
but no request ever leaves the machine.

Usage::

    python showcase_workspace.py --source <workspace> --role 吟风 \\
        --scene <memory|affection|proactive|channels|plugins> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/backend"), str(ROOT)]

from conversation.models import ThreadRecord  # noqa: E402
from conversation.service import (  # noqa: E402
    ConversationService,
    LegacySessionDescriptor,
)
from plugins.affection.backend.relationship.affection_service import (  # noqa: E402
    RoleAffectionService,
)
from core.roles.store import RoleStore  # noqa: E402
from plugins.default_memory.backend.semantic.store import MemoryStore2  # noqa: E402
from session.manager import SessionManager  # noqa: E402
from shiori_sdk.channels.message_source import MessageSource  # noqa: E402
from shiori_sdk.testing.memory import FakeMemoryStorage  # noqa: E402

MODEL_ID = "00000000-0000-4000-a000-0000000005ee"
CONFIG = f"""[[llm.registrations]]
id = "{MODEL_ID}"
provider = "openai"
model = "示例模型"
api_key = "showcase-offline"
base_url = "http://127.0.0.1:9/v1"
effort = "none"
model_context_window = 128000
model_max_output_tokens = 8192

[desktop.chat]
streaming_enabled = true

[plugins.memory_optimizer]
enabled = false

# Offline credentials so default_memory starts and the memory scene shows its
# timeline instead of "记忆已关闭"; nothing is embedded while capturing.
[plugins.default_memory]
embedding_api_key = "showcase-offline"
embedding_base_url = "http://127.0.0.1:9/v1"

[plugins.browser_use]
enabled = false
[plugins.computer_use]
enabled = false
[plugins.novelai]
enabled = false
[plugins.desktop_pet]
enabled = false
[plugins.default_memory]
enabled = true
"""

# The card fields worth a still; runtime wiring is rewritten for this workspace.
_CARD_FIELDS = (
    "id",
    "name",
    "description",
    "system_prompt",
    "background",
    "profile",
    "asset_categories",
    "asset_category_bindings",
    "affection_stage_prompts",
    "created_at",
    "updated_at",
)

Message = tuple[str, str, dict[str, Any]]


def copy_role(source: Path, name: str, workspace: Path) -> str:
    """Copies the named role's card and its pictures; returns the role id."""
    manifest = json.loads((source / "roles/roles.json").read_text(encoding="utf-8"))
    matches = [role for role in manifest["roles"] if role["name"] == name]
    if len(matches) != 1:
        raise SystemExit(f"{source} has {len(matches)} roles named {name!r}")
    role = matches[0]
    runtime = role["runtime_config"]
    # A mood may still be bound to a picture since deleted from the role.
    moods = {
        mood: path
        for mood, path in runtime["mood_illustration_bindings"].items()
        if (source / "roles" / path).is_file()
    }
    pictures = {
        path
        for path in (
            role["avatar"],
            role["chat_background"],
            *role["illustrations"],
            *moods.values(),
        )
        if path
    }
    for rel in pictures:
        target = workspace / "roles" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "roles" / rel, target)
    copied = {key: role[key] for key in _CARD_FIELDS}
    copied.update(
        avatar=role["avatar"],
        chat_background=role["chat_background"],
        illustrations=role["illustrations"],
        runtime_config={
            "default_mood": runtime["default_mood"],
            "mood_catalog": runtime["mood_catalog"],
            "mood_illustration_bindings": moods,
            "dialogue_model_registration_id": MODEL_ID,
            "visual_model_registration_id": MODEL_ID,
        },
        # Off: a proactive turn would only reach the closed model port.
        proactive={"enabled": False, "candidates": []},
        memory_init_state={
            "seed_first_impression_ready": True,
            "self_seed": {"status": "user_edited", "fingerprint": ""},
        },
    )
    roles_dir = workspace / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    (roles_dir / "roles.json").write_text(
        json.dumps(
            {"version": manifest["version"], "roles": [copied]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # Loading through the store validates the copied record.
    if RoleStore(workspace).get_role(role["id"]) is None:
        raise SystemExit("the copied role did not load")
    return role["id"]


class Clock:
    """Demo times: whole minutes counted back from the moment of the build."""

    def __init__(self) -> None:
        self.now = datetime.now().astimezone().replace(second=0, microsecond=0)

    def ago(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
        return self.now - timedelta(days=days, hours=hours, minutes=minutes)


# Every chat still's conversation fits the window whole: no message cut off
# at the top, and the newest one sits right above the composer.


def evening_chat(clock: Clock) -> list[Message]:
    """Last night's talk, where the memory and affection stills come from."""
    at = clock.ago(days=1, hours=2)
    return [
        ("user", "今天路过河边那家旧书店，你上次说想看的那本画集还在。", {"at": at}),
        (
            "assistant",
            "……哼，谁说想看了，我只是随口一提。\n\n"
            "不过既然你记着——下次带我一起去。别误会，是怕你又挑错书。",
            {"at": at + timedelta(minutes=1)},
        ),
        (
            "user",
            "那就周六下午？顺便去吃你说的那家草莓蛋糕。",
            {"at": at + timedelta(minutes=3)},
        ),
        (
            "assistant",
            "周六下午。说好了就不许反悔，笨蛋。\n要靠窗的位子。",
            {"at": at + timedelta(minutes=4)},
        ),
    ]


def proactive_chat(clock: Clock) -> list[Message]:
    """A quiet day after last night, then she speaks first, twice."""
    night = clock.ago(days=1, hours=1)
    return [
        *evening_chat(clock)[2:],
        ("user", "晚安，明天一早还要开会。", {"at": night}),
        (
            "assistant",
            "……晚安。不许再熬夜了。",
            {"at": night + timedelta(minutes=1)},
        ),
        (
            "assistant",
            "喂。一整天都没动静，是被工作吃掉了吗。",
            {"at": clock.ago(minutes=26), "proactive": True},
        ),
        (
            "assistant",
            "……我才不是在等你回消息。只是周六靠窗的位子，要提前订而已。",
            {"at": clock.ago(minutes=3), "proactive": True},
        ),
    ]


def tools_chat(clock: Clock) -> list[Message]:
    """She reads a file, searches and runs a shell command for the Saturday plan."""
    at = clock.ago(minutes=12)
    calls = [
        (
            "read_file",
            {"path": "旅行清单.md"},
            "- [x] 相机\n- [x] 帆布包\n- [ ] 雨伞\n- [ ] 充电宝",
        ),
        (
            "web_search",
            {"query": "本周六 下午 天气预报"},
            "周六：多云转小雨，午后降水概率 60%，气温 16–21℃。",
        ),
        (
            "shell",
            {"command": 'mkdir "周六散步"', "description": "新建放照片的文件夹"},
            "",
        ),
    ]
    tool_chain = [
        {
            "text": "",
            "reasoning_content": "",
            "calls": [
                {
                    "call_id": f"showcase-call-{index}",
                    "name": name,
                    "status": "success",
                    "arguments": arguments,
                    "final_arguments": arguments,
                    "result": result,
                }
                for index, (name, arguments, result) in enumerate(calls)
            ],
        }
    ]
    return [
        *evening_chat(clock)[2:],
        (
            "user",
            "帮我把周六理一下：看看旅行清单还缺什么，查查会不会下雨，"
            "再建个文件夹放照片。",
            {"at": at},
        ),
        (
            "assistant",
            "清单里还差雨伞和充电宝。周六午后有小雨，伞就由你来带。\n"
            "放照片的文件夹也建好了，叫「周六散步」。\n\n"
            "……这种小事，下次自己记着啦。",
            {"at": at + timedelta(minutes=1), "tool_chain": tool_chain},
        ),
    ]


def channels_chat(clock: Clock) -> list[Message]:
    """Only her line: the phone opens over the right of the chat."""
    return [
        (
            "assistant",
            "我去手机上回一下群消息。……不许偷看。",
            {"at": clock.ago(minutes=10)},
        )
    ]


def write_chat(workspace: Path, role_id: str, messages: list[Message]) -> None:
    manager = SessionManager(workspace)
    session = manager.get_or_create(f"role:{role_id}")
    for role, content, extra in messages:
        fields = dict(extra)
        fields["timestamp"] = fields.pop("at").isoformat()
        session.add_message(role, content, **fields)
    last = messages[-1][2]["at"].isoformat()
    session.metadata.update(
        current_mood="害羞",
        current_thought="周六的位子……还是我来订吧。",
        current_mood_updated_at=last,
        current_thought_updated_at=last,
    )
    manager.save(session)


def write_relationship(workspace: Path, role_id: str, clock: Clock) -> None:
    """Affection in 朋友 after a few small steps, tags, and a low loneliness."""
    affection = RoleAffectionService(workspace)
    # A short history, so the whole tab fits the still; no gap between
    # entries reaches the 72-hour decay.
    steps = [
        (clock.ago(days=1, hours=6, minutes=51), 1, "下雨天提醒我带伞"),
        (
            clock.ago(days=1, hours=1, minutes=56),
            2,
            "约好周六下午，还记得要靠窗的位子",
        ),
    ]
    affection.initialize(
        role_id,
        value=38,
        reason="已经聊过很多次，算是熟悉了",
        now=clock.ago(days=2, hours=4, minutes=20),
    )
    for at, delta, reason in steps:
        affection.record_user_activity(role_id, now=at)
        _ = affection.apply_delta(
            role_id, delta=delta, reason=reason, source="turn", now=at
        )
    now = clock.now.isoformat()
    state = workspace / "roles" / role_id / "state"
    snapshot = {
        "role_id": role_id,
        "role_self_view": "我嘴上说随便，其实早就把周六空出来了。",
        "relation_tags": ["嘴硬心软", "有点黏人", "约好周六"],
        "internal_profile": {},
        "source_summary": {},
        "generated_at": now,
        "last_attempted_at": now,
        "last_source_message_count": 0,
        "last_error": "",
    }
    loneliness = {
        "role_id": role_id,
        "loneliness_value": 18.0,
        "last_calculated_at": now,
        "last_user_at": clock.ago(days=1, hours=1).isoformat(),
        "last_proactive_at": "",
        "awaiting_reply_after_proactive": False,
        "awaiting_reply_since": "",
        "last_triggered_at": "",
        "cooldown_until": "",
    }
    for name, payload in (
        ("relationship_snapshot.json", snapshot),
        ("loneliness_runtime.json", loneliness),
    ):
        (state / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def write_memories(workspace: Path, role_id: str, clock: Clock) -> None:
    """Long-term memories she keeps about the user, as the timeline lists them."""
    store = MemoryStore2(
        workspace / "plugin-data/default_memory/memory2.db",
        open_database=FakeMemoryStorage().open_database,
    )
    scope: dict[str, object] = {
        "role_id": role_id,
        "scope_channel": "desktop",
        "scope_chat_id": f"role:{role_id}",
    }
    # Oldest first, as they were written down: (type, summary, category, when, weight).
    items: list[tuple[str, str, str, datetime, int]] = [
        (
            "event",
            "你说小时候在海边住过一个夏天，记得灯塔晚上一闪一闪的。",
            "",
            clock.ago(days=6, hours=3, minutes=14),
            2,
        ),
        ("preference", "你喝咖啡不加糖", "taste", clock.ago(days=4, hours=7), 0),
        (
            "profile",
            "你最近在赶一个项目，常常忙到很晚",
            "status",
            clock.ago(days=4, hours=1, minutes=33),
            1,
        ),
        (
            "event",
            "你路过河边的旧书店，我想看的那本画集还在，我们约好周六下午一起去，"
            "再去吃草莓蛋糕。",
            "",
            clock.ago(days=1, hours=2),
            3,
        ),
        (
            "profile",
            "你答应周六下午陪我去旧书店",
            "decision",
            clock.ago(days=1, hours=1, minutes=55),
            3,
        ),
    ]
    try:
        for memory_type, summary, category, happened, weight in items:
            store.upsert_item(
                memory_type,
                summary,
                None,
                source_ref=f"role:{role_id}@showcase",
                extra={"category": category, **scope} if category else scope,
                happened_at=happened.isoformat(timespec="minutes"),
                emotional_weight=weight,
            )
    finally:
        store.close()


def write_kv(workspace: Path, plugin_id: str, values: dict[str, Any]) -> None:
    path = workspace / "plugin-data" / plugin_id / "kv.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def write_channels(workspace: Path, role_id: str, clock: Clock) -> None:
    """Her Telegram, QQ and Feishu accounts and a conversation on each.

    Every account is saved with its connection off, so the plugins register
    it for the phone without ever dialing out with the made-up credential.
    """
    write_kv(
        workspace,
        "telegram",
        {
            "bots": [
                {
                    "ref": "8000000001",
                    "bot_id": "8000000001",
                    "token": "showcase-offline",
                    "enabled": False,
                    "role_id": role_id,
                }
            ]
        },
    )
    qq = workspace / "plugin-data/qq/accounts.json"
    qq.parent.mkdir(parents=True, exist_ok=True)
    qq.write_text(
        json.dumps(
            {
                "version": 1,
                "accounts": [
                    {
                        "ref": "showcase",
                        "ws_uri": "",
                        "ws_token": "",
                        "expected_uin": "10001",
                        "display_name": "吟风",
                        "avatar": "",
                        "timeout_seconds": 5.0,
                        "auto_connect": False,
                        "verified": True,
                        "mode": "managed",
                        "role_id": role_id,
                        "response_rules": None,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_kv(
        workspace,
        "feishu",
        {
            "applications": [
                {
                    "app_id": "cli_showcase",
                    "domain": "feishu",
                    "connection_enabled": False,
                    "role_id": role_id,
                }
            ]
        },
    )

    manager = SessionManager(workspace)
    conversation = ConversationService(manager)
    session = manager.get_or_create(f"role:{role_id}")

    def thread(channel: str, chat_id: str, name: str) -> ThreadRecord:
        record = conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{channel}:{chat_id}",
                role_id=role_id,
                channel=channel,
                chat_id=chat_id,
            )
        )
        conversation.remember_contact_name(record, name)
        return record

    def say(
        record: ThreadRecord,
        chat_type: str,
        at: datetime,
        content: str,
        sender: str | None = None,
    ) -> None:
        metadata: dict[str, Any] = {"thread_id": record.id, "chat_type": chat_type}
        if sender is not None:
            metadata["message_source"] = MessageSource(
                channel=record.channel,
                chat_id=record.external_thread_id,
                chat_type=chat_type,
                sender_id=f"showcase-{sender}",
                sender_name=sender,
            ).to_metadata()
        session.add_message(
            "user" if sender else "assistant",
            content,
            timestamp=at.isoformat(),
            metadata=metadata,
        )

    telegram = thread("telegram_8000000001", "100", "悠")
    group = thread("qq", "gqq:5", "周末读书会")
    feishu = thread("feishu:feishu:cli_showcase", "oc_1", "悠")
    say(feishu, "private", clock.ago(hours=5), "下午三点的会别忘了，要点我整理好了。")
    say(feishu, "private", clock.ago(hours=4, minutes=58), "收到，谢啦", "悠")
    say(telegram, "private", clock.ago(hours=2), "到家了吗？今天风有点大，记得关窗。")
    say(telegram, "private", clock.ago(hours=1, minutes=58), "刚到，窗也关好了", "悠")
    say(telegram, "private", clock.ago(hours=1, minutes=57), "……那就好。我才没有担心。")
    # The group the channels still opens: newest, so it tops the phone's list too.
    for minutes, content, sender in (
        (16, "周六有人去河边那家旧书店吗？听说在清仓", "阿花"),
        (15, "我周六加班……", "小林"),
        (14, "我去", "悠"),
        (13, "@阿花 他周六有约了。……跟我。", None),
        (12, "哦——", "阿花"),
        (12, "哦——", "小林"),
        (11, "……看什么看。书店又不是你们家开的。", None),
    ):
        say(group, "group", clock.ago(minutes=minutes), content, sender)
    manager.save(session)


SCENES: dict[str, Callable[[Clock], list[Message]]] = {
    "memory": evening_chat,
    "affection": evening_chat,
    "proactive": proactive_chat,
    "channels": channels_chat,
    "plugins": tools_chat,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--scene", choices=sorted(SCENES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    workspace: Path = args.out
    if workspace.exists():
        raise SystemExit(f"{workspace} already exists: give a fresh directory")
    workspace.mkdir(parents=True)
    (workspace / "config.toml").write_text(CONFIG, encoding="utf-8")
    clock = Clock()
    role_id = copy_role(args.source, args.role, workspace)
    write_chat(workspace, role_id, SCENES[args.scene](clock))
    write_relationship(workspace, role_id, clock)
    write_memories(workspace, role_id, clock)
    if args.scene == "channels":
        write_channels(workspace, role_id, clock)
    print(json.dumps({"role_id": role_id}))


if __name__ == "__main__":
    main()
