from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.context import ContextBuilder, ContextRequest, MessageEnvelopeBuilder
from agent.prompting import SYSTEM_CONTEXT_FRAME_MARKER
from bus.events import InboundMessage
from core.common.channel_directory import ChannelDirectory
from core.common.message_source import MessageSource
from core.roles import RoleStore
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY
from session.manager.models import Session


def test_message_envelope_preserves_group_members_across_desktop_followup():
    session = Session(key="role:mira")
    for sender in ("11", "22"):
        session.add_message(
            "user",
            "群里的消息",
            metadata={
                "transport_channel": "qq",
                "transport_chat_id": "gqq:123",
                "chat_type": "group",
                "sender_id": sender,
            },
        )
    desktop_message = InboundMessage(
        channel="desktop",
        sender="desktop",
        chat_id="role:mira",
        content="刚才群里是谁说的？",
        metadata={"chat_type": "desktop"},
    )

    messages = MessageEnvelopeBuilder().build(
        history=session.get_history(),
        current_message=desktop_message.content,
        system_prompt="role",
        context_frame="",
        channel=desktop_message.channel,
        chat_id=desktop_message.chat_id,
        message_source=MessageSource.from_inbound(desktop_message),
        message_timestamp=desktop_message.timestamp,
        media=None,
    )

    assert '"sender_id": "11"' in messages[1]["content"]
    assert '"sender_id": "22"' in messages[2]["content"]
    assert '"chat_id": "gqq:123"' in messages[1]["content"]
    assert '"channel": "desktop"' in messages[3]["content"]
    assert '"chat_id": "role:mira"' in messages[3]["content"]
    assert messages[3]["content"].endswith("刚才群里是谁说的？")


def test_context_builder_injects_interrupted_turn_as_separate_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class _Skills:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def get_always_skills(self) -> list[str]:
            return []

        def load_skills_for_context(self, names: list[str]) -> str:
            return ""

        def build_skills_summary(self) -> str:
            return ""

    class _Memory:
        def read_profile(self) -> str:
            return ""

        def read_self(self) -> str:
            return ""

        def read_recent_context(self) -> str:
            return ""

        def get_memory_context(self) -> str:
            return ""

    monkeypatch.setattr("agent.context.SkillsLoader", _Skills)
    monkeypatch.setattr(
        "agent.context.build_agent_static_identity_prompt", lambda **_: "identity"
    )
    monkeypatch.setattr("agent.context.build_skills_catalog_prompt", lambda text: text)
    RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test role",
    )
    builder = ContextBuilder(tmp_path, _Memory())  # type: ignore[arg-type]
    result = builder.render(
        ContextRequest(
            history=[
                {
                    "role": "assistant",
                    "content": "partial",
                    "reasoning_content": "retain-cot",
                }
            ],
            current_message="继续",
        ),
        session_metadata={
            "role_id": "mira",
            INTERRUPTED_TURN_METADATA_KEY: {"turn_id": "turn-1"},
        },
    )

    frame = result.messages[-2]
    assert frame["role"] == "user"
    assert "上一轮助手回复因用户主动中断而未完成" in frame["content"]
    assert result.messages[-3]["reasoning_content"] == "retain-cot"
    assert "interrupted" not in result.messages[-3].get("content", "")


def test_context_builder_builds_prompt_messages_and_assistant_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class _Skills:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def get_always_skills(self) -> list[str]:
            return ["always"]

        def load_skills_for_context(self, names: list[str]) -> str:
            return ",".join(names)

        def build_skills_summary(self) -> str:
            return "skill summary"

    class _Memory:
        def read_profile(self) -> str:
            return "memory block"

        def read_self(self) -> str:
            return "self note"

        def read_recent_context(self) -> str:
            return ""

        def get_memory_context(self) -> str:
            return "memory block"

    monkeypatch.setattr("agent.context.SkillsLoader", _Skills)
    monkeypatch.setattr(
        "agent.context.build_agent_static_identity_prompt", lambda **_: "identity"
    )
    monkeypatch.setattr(
        "agent.context.build_skills_catalog_prompt", lambda text: f"catalog:{text}"
    )

    image = tmp_path / "a.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    now = datetime.now(timezone.utc)
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="你现在要用更温柔的风格说话。",
        background="来自深海城的向导。",
        runtime_config={"shared_memory_enabled": True, "model": "deepseek-chat"},
    )
    role_metadata = {"role_id": "mira"}

    builder = ContextBuilder(tmp_path, _Memory())  # type: ignore[arg-type]
    result = builder.render(
        ContextRequest(
            history=[],
            current_message="",
            skill_names=["extra"],
            message_timestamp=now,
            retrieved_memory_block="retrieved",
        ),
        session_metadata=role_metadata,
    )
    prompt = result.system_prompt
    context_frame = result.messages[-2]["content"]
    assert "identity" in prompt
    assert "## 行为规范" in prompt
    assert "retrieved" not in prompt
    assert context_frame.startswith(SYSTEM_CONTEXT_FRAME_MARKER)
    assert "retrieved" in context_frame
    assert "memory block" in prompt
    assert "角色自我认知" in prompt
    assert "## 环境" in prompt
    assert "# Memes" not in prompt
    assert "<meme:shy>" not in prompt
    assert "catalog:skill summary" in prompt
    assert [item.name for item in builder.last_debug_breakdown][:3] == [
        "role_cache_prefix",
        "active_role",
        "identity",
    ]

    result2 = builder.render(
        ContextRequest(
            history=[],
            current_message="",
            skill_names=["extra"],
            message_timestamp=now,
            retrieved_memory_block="retrieved",
        ),
        session_metadata=role_metadata,
    )
    assert result2.system_prompt
    identity_meta = next(
        item for item in builder.last_debug_breakdown if item.name == "identity"
    )
    assert identity_meta.cache_hit is True

    messages = builder.render(
        ContextRequest(
            history=[{"role": "assistant", "content": "hi"}],
            current_message="hello",
            media=["https://img", str(image), str(tmp_path / "bad.txt")],
            skill_names=["extra"],
            channel="telegram",
            chat_id="42",
        ),
        session_metadata=role_metadata,
    ).messages
    assert messages[0]["role"] == "system"
    assert "## 环境" in messages[0]["content"]
    assert "## Current Session" in messages[0]["content"]
    assert messages[-1]["role"] == "user"
    assert len(messages[-1]["content"]) == 3
    stamped_message = messages[-1]["content"][-1]["text"]
    assert stamped_message.startswith("[当前消息时间:")
    assert "request_time=" in stamped_message
    assert "今天=" in stamped_message
    assert "昨天=" in stamped_message
    assert "明天=" in stamped_message
    assert "后天=" in stamped_message
    assert "weekday=" in stamped_message
    assert builder.last_assembled_contexts["turn_injection_context"] == {}

    turn_injection = builder.build_turn_injection_context(turn_injection_prompt="pref")
    render_result = builder.render(
        ContextRequest(
            history=[{"role": "assistant", "content": "hi"}],
            current_message="hello",
            media=["https://img", str(image), str(tmp_path / "bad.txt")],
            skill_names=["extra"],
            channel="telegram",
            chat_id="42",
            message_timestamp=now,
            turn_injection_prompt="pref",
        ),
        session_metadata=role_metadata,
    )
    assert render_result.system_prompt
    assert render_result.turn_injection_context == turn_injection
    assert render_result.messages
    assert render_result.messages[-2]["role"] == "user"
    assert render_result.messages[-2]["content"].startswith(SYSTEM_CONTEXT_FRAME_MARKER)
    assert "pref" in render_result.messages[-2]["content"]

    class _HintedChannel:
        def system_prompt_hint(self, chat_id: str) -> str:
            return f"## Channel rules\nchat={chat_id}\n"

    directory = ChannelDirectory()
    directory.bind({"telegram_work": _HintedChannel()}.get)
    builder.set_channel_directory(directory)

    def _system_prompt_for(channel: str) -> str:
        return builder.render(
            ContextRequest(
                history=[],
                current_message="hello",
                channel=channel,
                chat_id="42",
                message_timestamp=now,
            ),
            session_metadata=role_metadata,
        ).messages[0]["content"]

    hinted = _system_prompt_for("telegram_work")
    assert hinted.endswith("\n\n## Channel rules\nchat=42")
    assert "## Channel rules" not in _system_prompt_for("qqbot")

    media_only_messages = builder.render(
        ContextRequest(
            history=[],
            current_message="",
            media=["https://img"],
            skill_names=["extra"],
            message_timestamp=now,
        ),
        session_metadata=role_metadata,
    ).messages
    media_only_text = media_only_messages[-1]["content"][-1]["text"]
    assert media_only_text.startswith("[当前消息时间:")
    assert "request_time=" in media_only_text
    assert "今天=" in media_only_text

    text_media_builder = ContextBuilder(
        tmp_path,
        _Memory(),  # type: ignore[arg-type]
        multimodal=False,
    )
    text_media_messages = text_media_builder.render(
        ContextRequest(
            history=[],
            current_message="看看这张图",
            media=[str(image)],
            skill_names=["extra"],
            message_timestamp=now,
        ),
        session_metadata=role_metadata,
    ).messages
    text_media_content = text_media_messages[-1]["content"]
    assert isinstance(text_media_content, str)
    assert str(image) in text_media_content
    assert "当前模型不支持多模态，无法处理图片内容。" in text_media_content
    assert "image_url" not in text_media_content

    note_path = tmp_path / "chat-note.md"
    note_path.write_text("# note\n\nhello\n", encoding="utf-8")
    text_attachment_messages = builder.render(
        ContextRequest(
            history=[],
            current_message="这是附件",
            media=[str(note_path)],
            skill_names=["extra"],
            message_timestamp=now,
        ),
        session_metadata=role_metadata,
    ).messages
    text_attachment_content = text_attachment_messages[-1]["content"]
    assert isinstance(text_attachment_content, str)
    assert "[附加文件]" in text_attachment_content
    assert str(note_path) in text_attachment_content
    assert "read_file(path=" in text_attachment_content

    mixed_media_messages = builder.render(
        ContextRequest(
            history=[],
            current_message="图和文档都在这",
            media=[str(image), str(note_path)],
            skill_names=["extra"],
            message_timestamp=now,
        ),
        session_metadata=role_metadata,
    ).messages
    mixed_media_content = mixed_media_messages[-1]["content"]
    assert isinstance(mixed_media_content, list)
    assert mixed_media_content[-1]["type"] == "text"
    assert str(note_path) in mixed_media_content[-1]["text"]
    assert "read_file(path=" in mixed_media_content[-1]["text"]

    role_memory_root = tmp_path / "roles" / "mira" / "memory"
    role_memory_root.mkdir(parents=True, exist_ok=True)
    (role_memory_root / "SELF.md").write_text(
        "# 角色背景\n\n来自深海城的向导。\n", encoding="utf-8"
    )
    (role_memory_root / "MEMORY.md").write_text(
        "# 关系基线\n\n来源: seed:first_impression\n", encoding="utf-8"
    )
    role_messages = builder.render(
        ContextRequest(
            history=[],
            current_message="hello",
            skill_names=["extra"],
            message_timestamp=now,
        ),
        session_metadata={"role_id": "mira"},
    ).messages
    role_prompt = role_messages[0]["content"]
    assert "role_id=mira" in role_prompt
    assert "[role_background]" in role_prompt
    assert "[role_runtime_config]" in role_prompt
    assert "## Active Role: Mira" in role_prompt
    assert "你现在要用更温柔的风格说话。" in role_prompt
    assert "你是一个用户创建的角色" not in role_prompt
    assert "tool_search" in role_prompt

    role_prompt_cross_channel = builder.render(
        ContextRequest(
            history=[],
            current_message="hello",
            skill_names=["extra"],
            channel="telegram",
            chat_id="42",
            message_timestamp=now,
        ),
        session_metadata={"role_id": "mira"},
    ).messages[0]["content"]
    assert "role_id=mira" in role_prompt_cross_channel
    assert "[role_background]" in role_prompt_cross_channel
    role_prefix = role_prompt.split("## Active Role: Mira", 1)[0]
    role_prefix_cross_channel = role_prompt_cross_channel.split(
        "## Active Role: Mira", 1
    )[0]
    assert role_prefix == role_prefix_cross_channel


def test_context_builder_reproduces_temporal_conflict_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class _Skills:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def get_always_skills(self) -> list[str]:
            return []

        def load_skills_for_context(self, names: list[str]) -> str:
            return ""

        def build_skills_summary(self) -> str:
            return ""

    class _Memory:
        def read_profile(self) -> str:
            return ""

        def read_self(self) -> str:
            return ""

        def read_recent_context(self) -> str:
            return ""

        def get_memory_context(self) -> str:
            return ""

    monkeypatch.setattr("agent.context.SkillsLoader", _Skills)
    monkeypatch.setattr(
        "agent.context.build_agent_static_identity_prompt", lambda **_: "identity"
    )
    monkeypatch.setattr("agent.context.build_skills_catalog_prompt", lambda text: text)

    (tmp_path / "memes").mkdir()
    (tmp_path / "memes" / "manifest.json").write_text(
        '{"version":1,"categories":{}}',
        encoding="utf-8",
    )
    RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="你是 Mira。",
    )

    builder = ContextBuilder(tmp_path, _Memory())  # type: ignore[arg-type]
    request_time = datetime.fromisoformat("2026-04-08T17:57:00+08:00")
    retrieved_memory_block = """
[item_5a9c8d59f77c] [2026-03-29 12:44] 用户表示明天下午三点有面试，因当前感到疲惫想小睡，但担心此举会打乱明天的生物钟。
证据: 用户消息「明天我下午三点面试 我现在睡一会会打乱明天发生物钟吗有点疲惫」

[item_87aa0364de9e] [2026-03-29 14:42] 用户因午睡未成功，转为练习力扣题目以准备次日下午三点的字节跳动面试。
证据: 用户消息「没睡着做会力扣准备明天面试了」

[item_recent_interview] [2026-04-07 23:10] 用户提到 4 月 9 日（周四）下午 3 点的面试安排。
证据: 可回源原文「4 月 9 日（周四）下午 3 点」
""".strip()

    result = builder.render(
        ContextRequest(
            history=[],
            current_message="你还记得明天什么时候面试吗",
            channel="telegram",
            chat_id="7674283004",
            message_timestamp=request_time,
            retrieved_memory_block=retrieved_memory_block,
        ),
        session_metadata={"role_id": "mira"},
    )

    system_prompt = result.messages[0]["content"]
    context_frame = result.messages[-2]["content"]
    user_message = result.messages[-1]["content"]

    assert "request_time=2026-04-08T17:57:00+08:00" not in system_prompt
    assert "local_date=2026-04-08" not in system_prompt
    assert "今天=2026-04-08" not in system_prompt
    assert "明天=2026-04-09" not in system_prompt
    assert context_frame.startswith(SYSTEM_CONTEXT_FRAME_MARKER)
    assert "用户表示明天下午三点有面试" in context_frame
    assert "准备次日下午三点的字节跳动面试" in context_frame
    assert "4 月 9 日（周四）下午 3 点" in context_frame
    assert user_message.startswith("[当前消息时间: 2026-04-08 17:57:00")
    assert "request_time=2026-04-08T17:57:00+08:00" in user_message
    assert "今天=2026-04-08" in user_message
    assert "昨天=2026-04-07" in user_message
    assert "明天=2026-04-09" in user_message
    assert "后天=2026-04-10" in user_message
    assert "weekday=Wednesday" in user_message
    assert "相对时间以此为准" in user_message
    assert user_message.endswith("你还记得明天什么时候面试吗")
